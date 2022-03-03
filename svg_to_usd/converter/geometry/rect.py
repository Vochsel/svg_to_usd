from pxr import Usd, UsdGeom, Tf, Sdf, Gf
import logging
from .. import utils


def convert(usd_stage, prim_path, svg_rect):
    logging.debug("Creating rect")

    usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_rect, usd_mesh)

    try:
        svg_x = float(svg_rect.attrib['x'])
    except:
        svg_x = 0.0
    try:
        svg_y = float(svg_rect.attrib['y'])
    except:
        svg_y = 0.0

    try:
        svg_width = float(svg_rect.attrib['width'])
    except:
        svg_width = 1

    try:
        svg_height = float(svg_rect.attrib['height'])
    except:
        svg_height = 1

    usd_points = [
        utils.convert_position(svg_x, svg_y + svg_height),
        utils.convert_position(svg_x + svg_width, svg_y + svg_height),
        utils.convert_position(svg_x + svg_width, svg_y),
        utils.convert_position(svg_x, svg_y),
    ]

    usd_fvi = [0, 1, 2, 3]
    usd_fvc = [4]
    usd_uvs = [(0,0), (1, 0), (1,1), (0, 1)]

    usd_mesh.CreatePointsAttr().Set(usd_points)
    usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
    usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)
    usd_mesh.CreatePrimvar("st",
                           Sdf.ValueTypeNames.TexCoord2fArray,
                           UsdGeom.Tokens.vertex).Set(usd_uvs)

    return usd_mesh
