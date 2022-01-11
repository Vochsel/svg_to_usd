from pxr import UsdGeom
import logging
from .. import utils

from svgpath2mpl import parse_path


def convert(usd_stage, prim_path, svg_path):
    logging.debug("Creating polygon")

    if 'points' not in svg_path.attrib:
        # No path...
        logging.warning("SVG Path processed with no d attribute")
        return None

    _svg_points = svg_path.attrib['points']
    _svg_points = _svg_points.split(' ')
    _svg_points = [ i.split(',') for i in _svg_points ]

    usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_path, usd_mesh)

    usd_points = [utils.convert_position(float(p[0]), float(p[1])) for p in _svg_points]
    usd_fvi = [i for i in range(len(_svg_points))]
    usd_fvc = [len(_svg_points)]

    usd_mesh.CreatePointsAttr().Set(usd_points)
    usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
    usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)

    return usd_mesh
