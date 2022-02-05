from pxr import Usd

from .converter import common, utils
from .converter import conversion_context, conversion_options

import os


def convert_new(svg_path, usd_path):
    stage = Usd.Stage.CreateNew(usd_path)

    conversion_context['working_directory'] = os.path.dirname(usd_path)
    
    convert(svg_path, stage)
    
    stage.Save()
    return stage


def convert(svg_path, usd_stage):
    import xml.etree.ElementTree as ET

    tree = ET.parse(svg_path)
    root = tree.getroot()

    common.parent_map = {c: p for p in tree.iter() for c in p}

    # Setup utils

    conversion_context['texture_directory'] = os.path.join(conversion_context['working_directory'], 'tex')
    os.makedirs(conversion_context['texture_directory'], exist_ok=True)

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

    common.preprocess_svg_root(usd_stage, root)
    common.handle_svg_root(usd_stage, root)

    return usd_stage
