from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
from .. import utils
from .. import font
from pprint import pprint

from fontTools import ttLib
from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen

from svgpath2mpl import parse_path


class SVGPen(BasePen):
    def __init__(self, glyphSet):
        BasePen.__init__(self, glyphSet)
        self.d = ""
        self._lastX = self._lastY = None

    def _moveTo(self, pt):
        ptx, pty = self._isInt(pt)
        self.d += "M{} {}".format(ptx, pty)
        self._lastX, self._lastY = pt

    def _lineTo(self, pt):
        ptx, pty = self._isInt(pt)
        if (ptx, pty) == (self._lastX, self._lastY):
            return
        elif ptx == self._lastX:
            self.d += "V{}".format(pty)
        elif pty == self._lastY:
            self.d += "H{}".format(ptx)
        else:
            self.d += "L{} {}".format(ptx, pty)
        self._lastX, self._lastY = pt

    def _curveToOne(self, pt1, pt2, pt3):
        pt1x, pt1y = self._isInt(pt1)
        pt2x, pt2y = self._isInt(pt2)
        pt3x, pt3y = self._isInt(pt3)
        self.d += "C{} {} {} {} {} {}".format(pt1x, pt1y, pt2x, pt2y, pt3x, pt3y)
        self._lastX, self._lastY = pt3

    def _qCurveToOne(self, pt1, pt2):
        pt1x, pt1y = self._isInt(pt1)
        pt2x, pt2y = self._isInt(pt2)
        self.d += "Q{} {} {} {}".format(pt1x, pt1y, pt2x, pt2y)
        self._lastX, self._lastY = pt2

    def _closePath(self):
        self.d += "Z"
        self._lastX = self._lastY = None

    def _endPath(self):
        self._closePath()

    @staticmethod
    def _isInt(tup):
        return [int(flt) if (flt).is_integer() else flt for flt in tup]


def get_font_properties(element):
    """
    Get the base text attributes that all elements will use.
    The format and types returned are compatible with the Font Class

    Parameters
    ----------
    element : xml_element
        The svg element to be parsed.

    Returns
    -------
    properties : dict
        Font properties suitable for use in creating a Font instance.
    """

    svg_font_family = "Arial"  # TODO: Configurable fallback font
    svg_font_weight = None
    svg_font_style = 0
    svg_font_size = 144

    element_attributes = utils.parse_attributes(element)

    if "font-family" in element_attributes:
        svg_font_family = element_attributes["font-family"]

    if "font-weight" in element_attributes:
        svg_font_weight = element_attributes["font-weight"].lower()
        try:
            svg_font_weight = font.WEIGHTS[svg_font_weight]
        except:
            svg_font_weight = int(svg_font_weight)

    if "font-size" in element_attributes:
        svg_font_size = int(float(element_attributes["font-size"]))

    if "font-style" in element_attributes:
        if element_attributes["font-style"] == "italic":
            svg_font_style = 2

    if svg_font_weight == None:
        svg_font_weight = 400

    return {
        "family": svg_font_family,
        "size": svg_font_size,
        "weight": svg_font_weight,
        "style": svg_font_style,
    }


def create_usd_text_mesh(word, glyphSet, cmap, usd_mesh, units_per_em, font_size):
    svg_d = ""
    usd_points = []
    usd_fvi = []
    usd_fvc = []
    _charXOffset = 0

    for c in word:

        try:
            glyph = glyphSet[cmap[ord(c)]]
        except:
            glyph = glyphSet[".notdef"]
            continue

        if c == " ":
            _charXOffset += glyph.width
            continue

        pen = SVGPen(glyphSet)
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
            svg_path,
            usd_points,
            usd_fvi,
            usd_fvc,
            _charXOffset,
            0,
            1.0 / (units_per_em) * font_size,
        )

        _charXOffset += glyph.width

    usd_mesh.CreatePointsAttr().Set(usd_points)
    usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
    usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)

    return usd_mesh


def convert(usd_stage, prim_path, svg_text, fallback_font, type):
    if type == "geometry":
        return convert_as_geo(usd_stage, prim_path, svg_text, fallback_font)
    elif type == "schema":
        return convert_as_schema(usd_stage, prim_path, svg_text, fallback_font)


def convert_as_schema(usd_stage, prim_path, svg_text, fallback_font):
    logging.debug("Creating text: schema")

    font_props = get_font_properties(svg_text)
    element_attributes = utils.parse_attributes(svg_text)

    # initialise the generalised Font Class instance
    svg_font = font.Font(
        face_name=font_props["family"],
        size=font_props["size"],
        weight=font_props["weight"],
        style=font_props["style"],
    )

    # TODO: The creation of usd_font feels like it could be moved into the font class
    temp_weight = " {}".format(
        [k for k, v in font.WEIGHTS.items() if svg_font.weight == v][0].title()
    )
    if temp_weight == " Regular":
        temp_weight = ""
    temp_style = ""
    if svg_font.style == 2:
        temp_style = " Italic"
    usd_font = "{}{}{}".format(svg_font.findfontname(), temp_weight, temp_style)

    text_group = usd_stage.DefinePrim(prim_path, "Xform")
    logging.debug(svg_text)
    for tspan in svg_text:
        svg_word = " ".join(tspan.text.splitlines())
        tspan_attributes = utils.parse_attributes(tspan)

        # Sometimes tspans can be empty, we skip these
        if not svg_word:
            continue

        prim = usd_stage.DefinePrim(
            text_group.GetPath().AppendChild(
                Tf.MakeValidIdentifier("tspan_{}".format(svg_word))
            ),
            "Preliminary_Text",
        )
        prim.CreateAttribute("content", Sdf.ValueTypeNames.String).Set(svg_word)
        prim.CreateAttribute("font", Sdf.ValueTypeNames.StringArray).Set([usd_font])
        prim.CreateAttribute("depth", Sdf.ValueTypeNames.Float).Set(0.0)
        prim.CreateAttribute("horizontalAlignment", Sdf.ValueTypeNames.String).Set(
            "left"
        )
        prim.CreateAttribute("verticalAlignment", Sdf.ValueTypeNames.String).Set(
            "middle"
        )
        prim.CreateAttribute("pointSize", Sdf.ValueTypeNames.Float).Set(svg_font.size)
        prim.CreateAttribute("wrapMode", Sdf.ValueTypeNames.String).Set("flowing")
        prim.CreateAttribute("width", Sdf.ValueTypeNames.Float).Set(10)
        prim.CreateAttribute("height", Sdf.ValueTypeNames.Float).Set(10)
        if "id" in element_attributes:
            prim.CreateAttribute("id", Sdf.ValueTypeNames.String).Set(
                element_attributes["id"]
            )

        try:
            svg_x = float(tspan_attributes["x"])
        except:
            svg_x = 0.0
        try:
            svg_y = float(tspan_attributes["y"])
        except:
            svg_y = 0.0

        xform = UsdGeom.Xform(prim)

        xform.AddTransformOp(opSuffix="xy").Set(
            Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(svg_x, 0, svg_y))
        )

    return text_group


def convert_as_geo(usd_stage, prim_path, svg_text, fallback_font):

    # Might be a better place to put this. Needed for setting extents later.
    bboxCache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(), includedPurposes=[UsdGeom.Tokens.default_]
    )

    logging.debug("Creating text")
    text_root = None

    svg_fill = None
    font_path = ""
    gSet = None
    cmap = None
    t = None
    units_per_em = 2048

    element_attributes = utils.parse_attributes(svg_text)

    if "fill" in element_attributes:
        svg_fill = element_attributes["fill"]

    # Get the base font properties
    font_props = get_font_properties(svg_text)
    # Create a generalised Font instance
    svg_font = font.Font(
        face_name=font_props["family"],
        size=font_props["size"],
        weight=font_props["weight"],
        style=font_props["style"],
    )

    temp_weights = " {}".format(
        [" " + k for k, v in font.WEIGHTS.items() if svg_font.weight == v]
    )
    if svg_font.weight == 400:
        temp_weights = [""]
    temp_style = ""
    if svg_font.style == 2:
        temp_style = " italic"
    ft_styles = []
    for weight in temp_weights:
        style = "{}{}".format(weight, temp_style)
        if style.strip() == "":
            style = "regular"
        style = style.strip()
        ft_styles.append(style)

    # TODO Don't forget to add logic to handle url paths
    if "/" in font_props["family"] or "\\" in font_props["family"]:
        print("font_path", font_props["family"])
        font_path = font_props["family"]
    else:
        # print("Font:", svg_font)
        font_path = svg_font.findfont()

    try:
        ftfont = None
        if font_path.endswith("ttc"):
            fonts = ttLib.TTCollection(font_path)
            for fnt in fonts:
                name = fnt["name"]
                family = name.getBestFamilyName()
                style = name.getBestSubFamilyName()
                if family == svg_font.name and style.lower() in ft_styles:
                    ftfont = fnt
        else:
            ftfont = ttLib.TTFont(font_path)
        cmap = ftfont["cmap"]
        t = cmap.getBestCmap()
        units_per_em = ftfont["head"].unitsPerEm

        gSet = ftfont.getGlyphSet()
        ftfont.close()

    except ttLib.TTLibError:
        logging.error(f"ERROR: {fallback_font} cannot be processed.")
        return 1

    # Check if the text element has any children. Most likely <tspan> elements.
    if len(list(svg_text)) > 1:
        # Create an xform to hold the tspan elements.
        text_root = UsdGeom.Xform.Define(usd_stage, prim_path)

    # Check if the text element has any children. Most likely <tspan> elements.
    if len(list(svg_text)) > 1:
        # Create an xform to hold the tspan elements.
        text_root = UsdGeom.Xform.Define(usd_stage, prim_path)

        align = 0
        if "text-anchor" in element_attributes:
            svg_text_anchor = element_attributes["text-anchor"]
            if svg_text_anchor == "middle":
                align = -2
            elif svg_text_anchor == "end":
                align = -4

        for tspan in svg_text:
            svg_word = tspan.text
            tspan_attributes = utils.parse_attributes(tspan)

            # Sometimes tspans can be empty. We skip these
            if not svg_word:
                continue

            usd_mesh = UsdGeom.Mesh.Define(
                usd_stage,
                text_root.GetPath().AppendChild(
                    Tf.MakeValidIdentifier(
                        "tspan_{}_{}".format(svg_word, tspan_attributes["tree_id"])
                    )
                ),
            )
            # add parent fill colour if none exists
            if "fill" not in tspan_attributes:
                tspan_attributes["fill"] = svg_fill

            utils.handle_geom_attrs(tspan, usd_mesh)

            usd_mesh.AddTransformOp(opSuffix="align").Set(
                Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(align, 0, 0))
            )

            create_usd_text_mesh(
                svg_word, gSet, t, usd_mesh, units_per_em, svg_font.size
            )

            utils.set_extent(usd_mesh.GetPrim(), bboxCache)

    # Do this if the text element doesn't have any children elements.
    else:
        text_root = UsdGeom.Mesh.Define(usd_stage, prim_path)

        utils.handle_geom_attrs(svg_text, text_root)

        svg_word = svg_text.text

        if not svg_word and len(svg_text) > 0:
            # Hack to get first span
            svg_word = svg_text[0].text

        if not svg_word:
            return

        font_path = fallback_font

        align = 0
        if "text-anchor" in element_attributes:
            svg_text_anchor = element_attributes["text-anchor"]
            if svg_text_anchor == "middle":
                align = -2
            elif svg_text_anchor == "end":
                align = -4

        text_root.AddTransformOp(opSuffix="align").Set(
            Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(align, 0, 0))
        )

        create_usd_text_mesh(svg_word, gSet, t, text_root, units_per_em, svg_font.size)

        utils.set_extent(text_root.GetPrim(), bboxCache)

    return text_root
