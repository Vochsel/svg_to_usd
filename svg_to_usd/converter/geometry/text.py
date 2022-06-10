from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
import subprocess
from .. import utils
from pprint import pprint

import os, sys

from fontTools import ttLib
from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen

from opentypesvg.__version__ import version as __version__
from opentypesvg.utils import (
    create_folder,
    create_nested_folder,
    final_message,
    get_gnames_to_save_in_nested_folder,
    get_output_folder_path,
    split_comma_sequence,
    validate_font_paths,
    write_file,
)
from pathlib import Path
from svgpath2mpl import parse_path

class SVGPen(BasePen):

    def __init__(self, glyphSet):
        BasePen.__init__(self, glyphSet)
        self.d = u''
        self._lastX = self._lastY = None

    def _moveTo(self, pt):
        ptx, pty = self._isInt(pt)
        self.d += u'M{} {}'.format(ptx, pty)
        self._lastX, self._lastY = pt

    def _lineTo(self, pt):
        ptx, pty = self._isInt(pt)
        if (ptx, pty) == (self._lastX, self._lastY):
            return
        elif ptx == self._lastX:
            self.d += u'V{}'.format(pty)
        elif pty == self._lastY:
            self.d += u'H{}'.format(ptx)
        else:
            self.d += u'L{} {}'.format(ptx, pty)
        self._lastX, self._lastY = pt

    def _curveToOne(self, pt1, pt2, pt3):
        pt1x, pt1y = self._isInt(pt1)
        pt2x, pt2y = self._isInt(pt2)
        pt3x, pt3y = self._isInt(pt3)
        self.d += u'C{} {} {} {} {} {}'.format(pt1x, pt1y, pt2x, pt2y,
                                               pt3x, pt3y)
        self._lastX, self._lastY = pt3

    def _qCurveToOne(self, pt1, pt2):
        pt1x, pt1y = self._isInt(pt1)
        pt2x, pt2y = self._isInt(pt2)
        self.d += u'Q{} {} {} {}'.format(pt1x, pt1y, pt2x, pt2y)
        self._lastX, self._lastY = pt2

    def _closePath(self):
        self.d += u'Z'
        self._lastX = self._lastY = None

    def _endPath(self):
        self._closePath()

    @staticmethod
    def _isInt(tup):
        return [int(flt) if (flt).is_integer() else flt for flt in tup]


# OS Font paths
try:
    _HOME = Path.home()
except Exception:  # Exceptions thrown by home() are not specified...
    _HOME = Path(os.devnull)  # Just an arbitrary path with no children.
MSFolders = \
    r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
MSFontDirectories = [
    r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts',
    r'SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts']
MSUserFontDirectories = [
    str(_HOME / 'AppData/Local/Microsoft/Windows/Fonts'),
    str(_HOME / 'AppData/Roaming/Microsoft/Windows/Fonts'),
]
X11FontDirectories = [
    # an old standard installation point
    "/usr/X11R6/lib/X11/fonts/TTF/",
    "/usr/X11/lib/X11/fonts",
    # here is the new standard location for fonts
    "/usr/share/fonts/",
    # documented as a good place to install new fonts
    "/usr/local/share/fonts/",
    # common application, not really useful
    "/usr/lib/openoffice/share/fonts/truetype/",
    # user fonts
    str((Path(os.environ.get('XDG_DATA_HOME') or _HOME / ".local/share"))
        / "fonts"),
    str(_HOME / ".fonts"),
]
OSXFontDirectories = [
    "/Library/Fonts/",
    "/Network/Library/Fonts/",
    "/System/Library/Fonts/",
    # fonts installed via MacPorts
    "/opt/local/share/fonts",
    # user fonts
    str(_HOME / "Library/Fonts"),
]

def get_fontext_synonyms(fontext):
    """
    Return a list of file extensions extensions that are synonyms for
    the given file extension *fileext*.
    """
    return {
        'afm': ['afm'],
        'otf': ['otf', 'ttc', 'ttf'],
        'ttc': ['otf', 'ttc', 'ttf'],
        'ttf': ['otf', 'ttc', 'ttf'],
    }[fontext]

def _get_win32_installed_fonts():
    """List the font paths known to the Windows registry."""
    import winreg
    items = set()
    # Search and resolve fonts listed in the registry.
    for domain, base_dirs in [
            (winreg.HKEY_LOCAL_MACHINE, [win32FontDirectory()]),  # System.
            (winreg.HKEY_CURRENT_USER, MSUserFontDirectories),  # User.
    ]:
        for base_dir in base_dirs:
            for reg_path in MSFontDirectories:
                try:
                    with winreg.OpenKey(domain, reg_path) as local:
                        for j in range(winreg.QueryInfoKey(local)[1]):
                            # value may contain the filename of the font or its
                            # absolute path.
                            key, value, tp = winreg.EnumValue(local, j)
                            if not isinstance(value, str):
                                continue
                            try:
                                # If value contains already an absolute path,
                                # then it is not changed further.
                                path = Path(base_dir, value).resolve()
                            except RuntimeError:
                                # Don't fail with invalid entries.
                                continue
                            items.add(path)
                except (OSError, MemoryError):
                    continue
    return items


def win32FontDirectory():
    r"""
    Return the user-specified font directory for Win32.  This is
    looked up from the registry key ::
      \\HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders\Fonts
    If the key is not found, ``%WINDIR%\Fonts`` will be returned.
    """
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MSFolders) as user:
            return winreg.QueryValueEx(user, 'Fonts')[0]
    except OSError:
        return os.path.join(os.environ['WINDIR'], 'Fonts')

def _get_fontconfig_fonts():
    """Cache and list the font paths known to ``fc-list``."""
    try:
        if b'--format' not in subprocess.check_output(['fc-list', '--help']):
            _log.warning(  # fontconfig 2.7 implemented --format.
                'Matplotlib needs fontconfig>=2.7 to query system fonts.')
            return []
        out = subprocess.check_output(['fc-list', '--format=%{file}\\n'])
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(os.fsdecode(fname)) for fname in out.split(b'\n')]


def list_fonts(directory, extensions):
    """
    Return a list of all fonts matching any of the extensions, found
    recursively under the directory.
    """
    extensions = ["." + ext for ext in extensions]
    return [os.path.join(dirpath, filename)
            # os.walk ignores access errors, unlike Path.glob.
            for dirpath, _, filenames in os.walk(directory)
            for filename in filenames
            if Path(filename).suffix.lower() in extensions]


def findSystemFonts(fontpaths=None, fontext='ttf'):
    """
    Search for fonts in the specified font paths.  If no paths are
    given, will use a standard set of system paths, as well as the
    list of fonts tracked by fontconfig if fontconfig is installed and
    available.  A list of TrueType fonts are returned by default with
    AFM fonts as an option.
    """
    fontfiles = set()
    fontexts = get_fontext_synonyms(fontext)

    if fontpaths is None:
        if sys.platform == 'win32':
            installed_fonts = _get_win32_installed_fonts()
            fontpaths = MSUserFontDirectories + [win32FontDirectory()]
        else:
            installed_fonts = _get_fontconfig_fonts()
            if sys.platform == 'darwin':
                fontpaths = [*X11FontDirectories, *OSXFontDirectories]
            else:
                fontpaths = X11FontDirectories
        fontfiles.update(str(path) for path in installed_fonts
                         if path.suffix.lower()[1:] in fontexts)

    elif isinstance(fontpaths, str):
        fontpaths = [fontpaths]

    for path in fontpaths:
        fontfiles.update(map(os.path.abspath, list_fonts(path, fontexts)))

    # print("fontfiles", fontfiles)
    ft_files = []
    font_dict = {}
    for fname in fontfiles:
        if os.path.exists(fname):
            # print("fname", fname)
            if fname.endswith("ttc"):
                fonts = ttLib.TTCollection(fname)
                for font in fonts:
                    name = font['name']
                    family_name = name.getBestFamilyName()
                    style = name.getBestSubFamilyName()
                    if fname not in font_dict.keys():
                       font_dict[fname] = [{"family": family_name, "style": style}]
                    else:
                    # This is going to break because it expects one family name and style per path.
                        font_dict[fname].append({"family": family_name, "style": style})
            else:        
                font = ttLib.TTFont(fname)
                name = font['name']
                family_name = name.getBestFamilyName()
                style = name.getBestSubFamilyName()
                font_dict[fname] = [{"family": family_name, "style": style}]
                dir = os.path.dirname(fname)
                basename = os.path.basename(fname).lower()
                ft_files.append(os.path.join(dir, basename))

    
    # ft_files = [os.path.basename(fname).lower() for fname in fontfiles if os.path.exists(fname)] 
    # pprint(ft_files)
    # print("font_dict", font_dict) 
    # return [fname for fname in fontfiles if os.path.exists(fname)]
    # return ft_files
    return font_dict

#What would be a better way to create this dictionary once and reuse it?
font_dict = findSystemFonts()

font_weights = {
    100: "Hairline",
    200: "Thin",
    300: "Light",
    400: "Normal",
    500: "Medium",
    600: "Semibold",
    700: "Bold",
    800: "Extrabold",
    900: "Black"
}


def find_font_file(family, style):

    # font_dict = findSystemFonts(fontpaths="/Library/Fonts")
    # font_dict = findSystemFonts()
    matches = []
    for key in font_dict:
        for i in range(len(font_dict[key])):
        # print("key", key)
        # print("family", family)
        # print("style", style)
            if font_dict[key][i]["family"] == family and font_dict[key][i]["style"] == style:
                matches.append(key)

    return matches

def convert(usd_stage, prim_path, svg_text, fallback_font, type):
    if type == "geometry":
        return convert_as_geo(usd_stage, prim_path, svg_text, fallback_font)
    elif type == "schema":
        return convert_as_schema(usd_stage, prim_path, svg_text, fallback_font)

def convert_as_schema(usd_stage, prim_path, svg_text, fallback_font):
    logging.debug("Creating text: schema")
    
    # svg_word = svg_text.text
    # if not svg_word.strip():
    #     # Hack to get first span
    #     svg_word = svg_text[0].text

    # if not svg_word:
    #     return

    svg_font_family = "Arial" # TODO: Configurable fallback font
    if 'font-family' in svg_text.attrib:
        svg_font_family = svg_text.attrib['font-family']

    # TODO: This is probably buggy
    svg_font_weight = ""
    if 'font-weight' in svg_text.attrib:
        svg_font_weight = svg_text.attrib['font-weight'].capitalize()
        svg_font_family += "-" + svg_font_weight

    svg_font_size = 144
    if 'font-size' in svg_text.attrib:
        svg_font_size = float(svg_text.attrib['font-size']) 

    text_group = usd_stage.DefinePrim(prim_path, "Xform")
    logging.debug(svg_text)
    for tspan in svg_text:
        # tspan
        svg_word = tspan.text

        # Sometimes tspans can be empty, we skip these
        if not svg_word:
            continue

        prim = usd_stage.DefinePrim(text_group.GetPath().AppendChild(Tf.MakeValidIdentifier("tspan_{}".format(svg_word))), "Preliminary_Text")
        prim.CreateAttribute("content", Sdf.ValueTypeNames.String).Set(svg_word)
        prim.CreateAttribute("font", Sdf.ValueTypeNames.StringArray).Set([svg_font_family])
        prim.CreateAttribute("depth", Sdf.ValueTypeNames.Float).Set(0.0)
        prim.CreateAttribute("horizontalAlignment", Sdf.ValueTypeNames.String).Set("left")
        prim.CreateAttribute("verticalAlignment", Sdf.ValueTypeNames.String).Set("middle")
        prim.CreateAttribute("pointSize", Sdf.ValueTypeNames.Float).Set(svg_font_size)
        prim.CreateAttribute("wrapMode", Sdf.ValueTypeNames.String).Set("flowing")
        prim.CreateAttribute("width", Sdf.ValueTypeNames.Float).Set(10)
        prim.CreateAttribute("height", Sdf.ValueTypeNames.Float).Set(10)


        try:
            svg_x = float(tspan.attrib['x'])
        except:
            svg_x = 0.0
        try:
            svg_y = float(tspan.attrib['y'])
        except:
            svg_y = 0.0

        # TODO: These should be xform ops
        prim.CreateAttribute("x", Sdf.ValueTypeNames.Float).Set(svg_x)
        prim.CreateAttribute("y", Sdf.ValueTypeNames.Float).Set(svg_y)

    return text_group

def convert_as_geo(usd_stage, prim_path, svg_text, fallback_font):
    logging.debug("Creating text")
    text_root = None

    #Check if the text element has any children. Most likely <tspan> elements.
    if(len(list(svg_text)) > 0):
        #Create an xform to hold the tspan elements.
        # text_root = usd_stage.DefinePrim(prim_path, "Xform")
        text_root = UsdGeom.Xform.Define(usd_stage, prim_path)

        #Get the root text attributes that all the tspan will use.
        svg_font_family = "Arial"
        svg_font_weight = None 
        svg_font_style = None
        svg_font_size = 16
        font_path = fallback_font
        gSet = None
        cmap = None
        t = None
        units_per_em = 2048


        if 'font-family' in svg_text.attrib:
            svg_font_family = svg_text.attrib['font-family']
            if 'font-style' in svg_text.attrib:
                svg_font_style = svg_text.attrib['font-style'].title()
            if 'font-weight' in svg_text.attrib:
                svg_font_weight = svg_text.attrib['font-weight']

            print("family: {}, style: {}, weight: {}".format(svg_font_family, svg_font_style, svg_font_weight))
            
            if svg_font_weight == None and svg_font_style == None:
                svg_font_style = "Regular"
            elif svg_font_weight and svg_font_style == None:
                try:
                    svg_font_style = font_weights[int(svg_font_weight)]
                except:
                    svg_font_style = svg_font_weight.title()
            elif svg_font_weight and svg_font_style:
                # print("both weight and style")
                try:
                    svg_font_style = "{} {}".format(font_weights[int(svg_font_weight)], svg_font_style)
                    # print("style:", svg_font_style)
                except:
                    svg_font_style = "{} {}".format(svg_font_weight.title(), svg_font_style)
                    # print("style:", svg_font_style) 

            if "/" in svg_font_family or "\\" in svg_font_family:
                print("font_path", svg_font_family)
                font_path = svg_font_family
            else:
                # print("svg font family, weight, style", svg_font_family, svg_font_style)
                m = find_font_file(svg_font_family, svg_font_style)
                print("m", m)
                font_path = m[-1]

            try:
                font = None
                if font_path.endswith("ttc"):
                        fonts = ttLib.TTCollection(font_path)
                        for fnt in fonts:
                            name = fnt['name']
                            family = name.getBestFamilyName()
                            style = name.getBestSubFamilyName()
                            # print("family - style: {}-{}".format(family, style))
                            if family == svg_font_family and style == svg_font_style:
                                font = fnt 
                else:
                    font = ttLib.TTFont(font_path)
                cmap = font['cmap']
                # t = cmap.getcmap(3, 1).cmap
                t = cmap.getBestCmap()
                units_per_em = font['head'].unitsPerEm

                gSet = font.getGlyphSet()
                font.close()

            except ttLib.TTLibError:
                logging.error(f"ERROR: {fallback_font} cannot be processed.")
                return 1

            if 'font-size' in svg_text.attrib:
                svg_font_size = (float(svg_text.attrib['font-size'].replace('px', '')))

            align = 0
            if 'text-anchor' in svg_text.attrib:
                svg_text_anchor = svg_text.attrib['text-anchor']
                if svg_text_anchor == "middle":
                    align = -2
                elif svg_text_anchor == "end":
                    align = -4

            # Ideally we'd want to add these transforms to the root but the transform order
            # is incorrect. We need translate, scale, but this gives us scale, translate.

            # text_root.AddTransformOp(opSuffix="text").Set(Gf.Matrix4d(1.0).SetScale(
            #     Gf.Vec3d(svg_font_size, svg_font_size, svg_font_size)))
            # text_root.AddTransformOp(opSuffix="align").Set(
            #     Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(align, 0, 0)))

            for tspan in svg_text:
                svg_word = tspan.text

                # Sometimes tspans can be empty. We skip these
                if not svg_word:
                    continue

                usd_mesh = UsdGeom.Mesh.Define(usd_stage, text_root.GetPath().AppendChild(Tf.MakeValidIdentifier("tspan_{}_{}".format(svg_word, tspan.attrib['tree_id']))))
                # print("usd_mesh BEFORE handle attr:", usd_mesh)
                # usd_mesh = usd_stage.DefinePrim(text_root.GetPath().AppendChild(Tf.MakeValidIdentifier("tspan_{}".format(svg_word))), "Mesh")
                utils.handle_geom_attrs(tspan, usd_mesh) 

                usd_mesh.AddTransformOp(opSuffix="text").Set(Gf.Matrix4d(1.0).SetScale(
                    Gf.Vec3d(svg_font_size, svg_font_size, svg_font_size)))
                usd_mesh.AddTransformOp(opSuffix="align").Set(
                    Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(align, 0, 0)))

                svg_d = ""

                usd_points = []
                usd_fvi = []
                usd_fvc = []
                _charXOffset = 0

                for c in svg_word:

                    try:
                        glyph = gSet[t[ord(c)]]
                    except:
                        glyph = gSet['.notdef']
                        continue

                    if c == ' ':
                        _charXOffset += glyph.width
                        continue

                    pen = SVGPen(gSet)
                    tpen = TransformPen(pen, (1.0, 0.0, 0.0, -1.0, 0.0, 0.0))

                    glyph.draw(tpen)
                    svg_path = parse_path(pen.d)

                    d = pen.d

                    # Skip glyphs with no contours
                    if not len(d):
                        continue

                    svg_d = d

                    svg_path = parse_path(svg_d)

                    usd_points, usd_fvi, usd_fvc = utils.path_to_mesh(
                        svg_path, usd_points, usd_fvi, usd_fvc, _charXOffset, 0, 1.0/(units_per_em))

                    _charXOffset += glyph.width

                usd_mesh.CreatePointsAttr().Set(usd_points)
                usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
                usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)
    
    #Do this if the text element doesn't have any children elements.
    else:

        text_root = UsdGeom.Mesh.Define(usd_stage, prim_path)

        utils.handle_geom_attrs(svg_text, text_root)

        svg_word = svg_text.text
        
        if not svg_word:
            # Hack to get first span
            svg_word = svg_text[0].text

            # print(svg_word)

        if not svg_word:
            return
        svg_font_size = 16

        gSet = None

        cmap = None
        t = None
        units_per_em = 2048

        font_path = fallback_font

        if 'font-family' in svg_text.attrib:
            svg_font_family = svg_text.attrib['font-family']
            svg_font_style = None 
            svg_font_weight = None
            if 'font-style' in svg_text.attrib:
                svg_font_style = svg_text.attrib['font-style'].title()
            if 'font-weight' in svg_text.attrib:
                svg_font_weight = svg_text.attrib['font-weight']

            print("family: {}, style: {}, weight: {}".format(svg_font_family, svg_font_style, svg_font_weight))
            
            if svg_font_weight == None and svg_font_style == None:
                svg_font_style = "Regular"
            elif svg_font_weight and svg_font_style == None:
                try:
                    svg_font_style = font_weights[int(svg_font_weight)]
                except:
                    svg_font_style = svg_font_weight.title()
            elif svg_font_weight and svg_font_style:
                try:
                    svg_font_style = "{} {}".format(font_weights[int(svg_font_weight)], svg_font_style)
                except:
                    svg_font_style = "{} {}".format(svg_font_weight.title(), svg_font_style)

            if "/" in svg_font_family or "\\" in svg_font_family:
                print("font_path", svg_font_family)
                font_path = svg_font_family
            else:
                m = find_font_file(svg_font_family, svg_font_style)
                print("m", m)
                font_path = m[-1]

        # font_path = "/Library/Fonts/Yahoo Sans-Regular.otf"

        try:
            font = None
            if font_path.endswith("ttc"):
                    fonts = ttLib.TTCollection(font_path)
                    for fnt in fonts:
                        name = fnt['name']
                        family = name.getBestFamilyName()
                        style = name.getBestSubFamilyName()
                        # print("family - style: {}-{}".format(family, style))
                        if family == svg_font_family and style == svg_font_style:
                            font = fnt 
            else:
                font = ttLib.TTFont(font_path)
            cmap = font['cmap']
            # t = cmap.getcmap(3, 1).cmap
            t = cmap.getBestCmap()
            units_per_em = font['head'].unitsPerEm

            gSet = font.getGlyphSet()
            font.close()

        except ttLib.TTLibError:
            logging.error(f"ERROR: {fallback_font} cannot be processed.")
            return 1

        if 'font-size' in svg_text.attrib:
            svg_font_size = (float(svg_text.attrib['font-size'].replace('px', '')))

        align = 0
        if 'text-anchor' in svg_text.attrib:
            svg_text_anchor = svg_text.attrib['text-anchor']
            if svg_text_anchor == "middle":
                align = -2
            elif svg_text_anchor == "end":
                align = -4

        usd_mesh.AddTransformOp(opSuffix="text").Set(Gf.Matrix4d(1.0).SetScale(
            Gf.Vec3d(svg_font_size, svg_font_size, svg_font_size)))
        usd_mesh.AddTransformOp(opSuffix="align").Set(
            Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(align, 0, 0)))

        svg_d = ""

        usd_points = []
        usd_fvi = []
        usd_fvc = []
        _charXOffset = 0

        for c in svg_word:

            try:
                glyph = gSet[t[ord(c)]]
            except:
                glyph = gSet['.notdef']
                continue

            if c == ' ':
                _charXOffset += glyph.width
                continue

            pen = SVGPen(gSet)
            tpen = TransformPen(pen, (1.0, 0.0, 0.0, -1.0, 0.0, 0.0))

            glyph.draw(tpen)
            svg_path = parse_path(pen.d)

            d = pen.d

            # Skip glyphs with no contours
            if not len(d):
                continue

            svg_d = d

            svg_path = parse_path(svg_d)

            usd_points, usd_fvi, usd_fvc = utils.path_to_mesh(
                svg_path, usd_points, usd_fvi, usd_fvc, _charXOffset, 0, 1.0/(units_per_em))

            _charXOffset += glyph.width

        usd_mesh.CreatePointsAttr().Set(usd_points)
        usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
        usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)

    return text_root

