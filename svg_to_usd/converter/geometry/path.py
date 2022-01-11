from pxr import UsdGeom
import logging
from .. import utils

from svgpath2mpl import parse_path


def convert(usd_stage, prim_path, svg_path):
    logging.debug("Creating path")

    if 'd' not in svg_path.attrib:
        # No path...
        logging.warning("SVG Path processed with no d attribute")
        return None

    svg_d = svg_path.attrib['d']
    _path = parse_path(svg_d)
    _is_closed = _path.codes[-1] == _path.CLOSEPOLY

    if _is_closed:
        usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)
    else:
        usd_mesh = UsdGeom.BasisCurves.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_path, usd_mesh)

    usd_points = []
    usd_fvi = []
    usd_fvc = []

    if _is_closed:

        usd_points, usd_fvi, usd_fvc = utils.path_to_mesh(
            _path, usd_points, usd_fvi, usd_fvc)

        usd_mesh.CreatePointsAttr().Set(usd_points)
        usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
        usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)
    else:
        usd_points, usd_fvc = utils.path_to_curve(_path, usd_points, usd_fvc)
        usd_mesh.CreatePointsAttr().Set(usd_points)
        usd_mesh.CreateCurveVertexCountsAttr().Set(usd_fvc)

        usd_mesh.CreateTypeAttr().Set(UsdGeom.Tokens.linear)

    return usd_mesh
