from pxr import UsdGeom
import logging

from .. import utils
from .. import conversion_options


def convert(usd_stage, prim_path, svg_element):
    logging.debug("Creating xform")

    usd_mesh = UsdGeom.Xform.Define(usd_stage, prim_path)

    if conversion_options['transform_group']:
        utils.handle_xform_attrs(svg_element, usd_mesh)

    return usd_mesh
