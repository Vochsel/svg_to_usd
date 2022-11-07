from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
from .. import utils


def convert(usd_stage, prim_path, svg_element):
    logging.debug("Creating line")

    usd_mesh = UsdGeom.BasisCurves.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_element, usd_mesh)

    element_attributes = utils.parse_attributes(svg_element)

    _x1 = float(element_attributes["x1"]) if "x1" in element_attributes else 0.0
    _y1 = float(element_attributes["y1"]) if "y1" in element_attributes else 0.0
    _x2 = float(element_attributes["x2"]) if "x2" in element_attributes else 0.0
    _y2 = float(element_attributes["y2"]) if "y2" in element_attributes else 0.0

    _stroke_width = 1

    if "stroke-width" in element_attributes:
        _stroke_width = float(element_attributes["stroke-width"])
    usd_points = [
        utils.convert_position(_x1, _y1),
        utils.convert_position(_x2, _y2),
    ]
    usd_fvc = [2]
    usd_widths = [_stroke_width]

    usd_mesh.CreatePointsAttr().Set(usd_points)
    usd_mesh.CreateCurveVertexCountsAttr().Set(usd_fvc)
    usd_mesh.CreateWidthsAttr().Set(usd_widths)
    usd_mesh.SetWidthsInterpolation(UsdGeom.Tokens.constant)

    usd_mesh.CreateTypeAttr().Set(UsdGeom.Tokens.linear)

    return usd_mesh
