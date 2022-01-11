from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
from .. import utils

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


def convert(usd_stage, prim_path, svg_text, fallback_font):
    logging.debug("Creating text")

    usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_text, usd_mesh)

    svg_word = svg_text.text
    if not svg_word:
        return
    svg_font_size = 16

    gSet = None

    cmap = None
    t = None
    units_per_em = 2048

    try:
        font = ttLib.TTFont(fallback_font)
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
