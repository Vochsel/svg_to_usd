from pxr import UsdGeom
import math
import logging
from .. import utils, conversion_options

# TODO: Remove
PI = 3.141592


def convert(usd_stage, prim_path, svg_ellipse):
    logging.debug("Creating ellipse")

    usd_mesh = UsdGeom.Mesh.Define(usd_stage, prim_path)

    utils.handle_geom_attrs(svg_ellipse, usd_mesh)

    svg_x = float(svg_ellipse.attrib['cx'])
    svg_y = float(svg_ellipse.attrib['cy'])
    svg_rx = float(svg_ellipse.attrib['rx'])
    svg_ry = float(svg_ellipse.attrib['ry'])

    usd_points = []
    usd_fvi = []
    usd_fvc = [conversion_options['curve_resolution']]

    for i in range(conversion_options['curve_resolution']):
        iter = (i/conversion_options['curve_resolution']) * PI * 2
        usd_points.append(utils.convert_position(
            svg_x - (math.sin(iter) * svg_rx), svg_y - (math.cos(iter) * svg_ry)))
        usd_fvi.append(i)

    usd_mesh.CreatePointsAttr().Set(usd_points)
    usd_mesh.CreateFaceVertexIndicesAttr().Set(usd_fvi)
    usd_mesh.CreateFaceVertexCountsAttr().Set(usd_fvc)

    return usd_mesh
