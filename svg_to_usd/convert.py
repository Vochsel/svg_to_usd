from pxr import Usd

from .converter import common, utils
from .converter import conversion_context, conversion_options


def convert_new(svg_path, usd_path):
    stage = Usd.Stage.CreateNew(usd_path)
    
    convert(svg_path, stage)
    
    stage.Save()
    return stage


def convert(svg_path, usd_stage):
    import xml.etree.ElementTree as ET

    tree = ET.parse(svg_path)
    root = tree.getroot()

    common.parent_map = {c: p for p in tree.iter() for c in p}

    # Setup utils

    if conversion_options['up_axis'] == "x":
        utils.convert_position = utils.convert_position_x
    elif conversion_options['up_axis'] == "y":
        utils.convert_position = utils.convert_position_y
    elif conversion_options['up_axis'] == "z":
        utils.convert_position = utils.convert_position_z

    if 'width' in root.attrib:
        conversion_context['document_width'] = root.attrib['width']
    if 'height' in root.attrib:
        conversion_context['document_height'] = root.attrib['height']

    common.handle_svg_root(usd_stage, root)

    return usd_stage
