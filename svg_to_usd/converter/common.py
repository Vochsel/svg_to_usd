from pxr import Usd, UsdGeom, Sdf, UsdShade

import logging
import importlib

from . import utils
from .geometry import rect, circle, ellipse, path, line, text, group, polygon, polyline

importlib.reload(text)
importlib.reload(line)
from .fills import image
from . import conversion_options

# TODO: Handle this better
parent_map = {}

image_map = {}  # image_id -> usd_material
pattern_map = {}  # pattern_id -> image_id


def preprocess_element(usd_stage, svg_element, parent_prim=None):

    svg_id = utils.get_id(svg_element)

    prim_path = "{}".format(svg_id)

    if "image" in svg_element.tag and conversion_options["convert_image"]:
        prim_path = Sdf.Path("/materials/" + prim_path)
        usd_material = image.convert(usd_stage, prim_path, svg_element)
        image_map[svg_id] = usd_material

    if "pattern" in svg_element.tag and conversion_options["convert_image"]:
        if len(svg_element) > 0:
            if "{http://www.w3.org/1999/xlink}href" in svg_element[0].attrib:
                image_id = svg_element[0].attrib["{http://www.w3.org/1999/xlink}href"]
                pattern_map[svg_id] = image_id[1:]


def handle_element(usd_stage, svg_element, parent_prim=None):
    global parent_map

    if "clipPath" in parent_map[svg_element].tag:
        return

    element_attributes = utils.parse_attributes(svg_element)

    _visible = True

    if "fill" in element_attributes:
        if element_attributes["fill"] == "none":
            _visible = False
    if "opacity" in element_attributes:
        if element_attributes["opacity"] == "0":
            _visible = False
    if "display" in element_attributes:
        if element_attributes["display"] == "none":
            _visible = False
    # if "style" in svg_element.attrib:
    #     if "opacity: 0" in svg_element.attrib["style"]:
    #         _visible = False
    #     if "fill: none" in svg_element.attrib["style"]:
    #         _visible = False
    #     if "display: none" in svg_element.attrib["style"]:
    #         _visible = False

    svg_id = utils.get_id(svg_element)

    prim_path = "{}".format(svg_id)
    # Adding a text prefix because the return value could be a number.
    if svg_element.tag.rpartition("}")[-1] == "text" and "id" not in svg_element.attrib:
        prim_path = "text_{}".format(prim_path)

    if parent_prim:
        prim_path = parent_prim.GetPath().AppendPath(prim_path)
    else:
        prim_path = Sdf.Path("/" + prim_path)

    logging.debug("Prim path: {}".format(prim_path))
    usd_mesh = None

    if "rect" in svg_element.tag and conversion_options["convert_rect"]:
        usd_mesh = rect.convert(usd_stage, prim_path, svg_element)
    if "ellipse" in svg_element.tag and conversion_options["convert_ellipse"]:
        usd_mesh = ellipse.convert(usd_stage, prim_path, svg_element)
    if "circle" in svg_element.tag and conversion_options["convert_circle"]:
        usd_mesh = circle.convert(usd_stage, prim_path, svg_element)
    if "path" in svg_element.tag and conversion_options["convert_path"]:
        usd_mesh = path.convert(usd_stage, prim_path, svg_element)
    if "polygon" in svg_element.tag and conversion_options["convert_polygon"]:
        usd_mesh = polygon.convert(usd_stage, prim_path, svg_element)
    if "polyline" in svg_element.tag and conversion_options["convert_polyline"]:
        usd_mesh = polyline.convert(usd_stage, prim_path, svg_element)
    if (
        svg_element.tag.rpartition("}")[-1] == "line"
        and conversion_options["convert_line"]
    ):
        usd_mesh = line.convert(usd_stage, prim_path, svg_element)
    if (
        svg_element.tag.rpartition("}")[-1] == "text"
        and conversion_options["convert_text"]
    ):
        usd_mesh = text.convert(
            usd_stage,
            prim_path,
            svg_element,
            fallback_font=conversion_options["fallback_font"],
            type=conversion_options["text_type"],
        )
    if (
        svg_element.tag.rpartition("}")[-1] == "g"
        and conversion_options["convert_group"]
    ):
        usd_mesh = group.convert(usd_stage, prim_path, svg_element)

    if not usd_mesh:
        # Something has failed in generation, or unsupported svg element
        logging.debug(f"SVG tag '{svg_element.tag}' unsupported")
        return

    # TODO: Handle visibility properly
    if "visibility" in element_attributes:
        if element_attributes["visibility"] == "hidden":
            _visible = False

    # Author visibility
    if not _visible:
        if (
            "force_visibility" in conversion_options
            and conversion_options["force_visibility"] == True
        ):
            pass
        else:
            usd_mesh.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

    return usd_mesh


def preprocess_svg_root(stage, root, parent_prim=None):
    for elem in root:
        preprocess_element(stage, elem, parent_prim)
        preprocess_svg_root(stage, elem, None)


def handle_svg_root(stage, root, parent_prim=None):
    for elem in root:
        usd_prim = handle_element(stage, elem, parent_prim)
        handle_svg_root(stage, elem, usd_prim)
