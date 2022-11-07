from pxr import UsdGeom
import logging
from .. import utils

from svgpath2mpl import parse_path


def convert(usd_stage, prim_path, svg_path):
    logging.debug("Creating polygon")

    element_attributes = utils.parse_attributes(svg_path)

    if "points" not in element_attributes:
        # No path...
        logging.warning("SVG Path processed with no d attribute")
        return None

    _svg_points = element_attributes["points"]
    _svg_points = _svg_points.split(" ")
    _svg_points = [i.split(",") for i in _svg_points]
    # _is_closed = _path.codes[-1] == _path.CLOSEPOLY
    _is_closed = True

    # TODO: This may no longer work with the introduction of the parse_attributes function.
    if "fill" in element_attributes:
        if element_attributes["fill"] == "none":
            _is_closed = False
        else:
            _is_closed = True

    if _is_closed:
        usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)
    else:
        usd_mesh = UsdGeom.BasisCurves.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_path, usd_mesh)

    usd_points = [utils.convert_position(float(p[0]), float(p[1])) for p in _svg_points]

    if _is_closed:

        usd_fvi = [i for i in range(len(_svg_points))] + [0]
        usd_fvc = [len(_svg_points) + 1]

        usd_mesh.CreatePointsAttr().Set(usd_points)
        usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
        usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)
    else:
        usd_fvi = [i for i in range(len(_svg_points))]
        usd_fvc = [len(_svg_points)]
        usd_mesh.CreatePointsAttr().Set(usd_points)
        usd_mesh.CreateCurveVertexCountsAttr().Set(usd_fvc)

        usd_mesh.CreateTypeAttr().Set(UsdGeom.Tokens.linear)

    return usd_mesh
