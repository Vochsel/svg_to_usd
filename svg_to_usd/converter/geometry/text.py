from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
from .. import utils

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

    return [fname for fname in fontfiles if os.path.exists(fname)]




def find_font_file(query):
    matches = list(filter(lambda path: query.lower() in os.path.basename(path), findSystemFonts()))
    return matches

def convert(usd_stage, prim_path, svg_text, fallback_font):
    logging.debug("Creating text")

    usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_text, usd_mesh)

    svg_word = svg_text.text
    print(svg_word)
    
    if not svg_word:
        # Hack to get first span
        svg_word = svg_text[0].text
        for child in svg_text:
            print(child)

        print(svg_word)

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

        if "/" in svg_font_family or "\\" in svg_font_family:
            font_path = svg_font_family
        else:
            print(svg_font_family)
            m = find_font_file(svg_font_family)
            print(m)
            font_path = m[-1]

    try:
        font = ttLib.TTFont(font_path)
        cmap = font['cmap']
        t = cmap.getcmap(3, 1).cmap
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
            svg_path, usd_points, usd_fvi, usd_fvc, _charXOffset, 0, 1.0/(units_per_em * 1.33333))

        _charXOffset += glyph.width

    usd_mesh.CreatePointsAttr().Set(usd_points)
    usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
    usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)

    return usd_mesh
