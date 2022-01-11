from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
from .. import utils


def convert(usd_stage, prim_path, svg_element):
    logging.debug("Creating line")

    usd_mesh = UsdGeom.BasisCurves.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_element, usd_mesh)

    _x1 = float(svg_element.attrib['x1']
                ) if 'x1' in svg_element.attrib else 0.0
    _y1 = float(svg_element.attrib['y1']
                ) if 'y1' in svg_element.attrib else 0.0
    _x2 = float(svg_element.attrib['x2']
                ) if 'x2' in svg_element.attrib else 0.0
    _y2 = float(svg_element.attrib['y2']
                ) if 'y2' in svg_element.attrib else 0.0

    _stroke_width = 1

    if "stroke-width" in svg_element.attrib:
        _stroke_width = svg_element.attrib["stroke-width"]

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
