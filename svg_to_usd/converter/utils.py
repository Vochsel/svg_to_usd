from pxr import Gf, Usd, UsdGeom, Tf, Sdf, UsdShade
import re
import logging

import matplotlib.patches
from . import common

ELLIPSIS_RES = 32
UP_AXIS = "Y"

ID_COUNT = 0


def get_id(svg_element):
    global ID_COUNT

    if 'id' in svg_element.attrib:
        return Tf.MakeValidIdentifier(svg_element.attrib['id'])

    ID_COUNT += 1

    return "ob_{}".format(ID_COUNT)


def default_normal():
    return Gf.Vec3f(0, 1, 0)


convert_position = None


def convert_position_x(svg_x, svg_y, vec_class=Gf.Vec3f):
    return vec_class(0, -svg_y, svg_x)


def convert_position_y(svg_x, svg_y, vec_class=Gf.Vec3f):
    return vec_class(svg_x, 0, svg_y)


def convert_position_z(svg_x, svg_y, vec_class=Gf.Vec3f):
    return vec_class(svg_x, -svg_y, 0)


def convert_type(val):
    if type(val) == bool:
        return Sdf.ValueTypeNames.Boolean
    elif type(val) == int:
        return Sdf.ValueTypeNames.Integer
    elif type(val) == float:
        return Sdf.ValueTypeNames.Float
    elif type(val) == str:
        return Sdf.ValueTypeNames.String
    else:
        return None


def literal_to_rgb(literal):
    _dict = {
        "aqua": "#00ffff",
        "black": "#000000",
        "blue": "#0000ff",
        "fuchsia": "#ff00ff",
        "green": "#008000",
        "grey": "#808080",
        "lime": "#00ff00",
        "maroon": "#800000",
        "navy": "#000080",
        "olive": "#808000",
        "purple": "#800080",
        "red": "#ff0000",
        "silver": "#c0c0c0",
        "teal": "#008080",
        "white": "#ffffff",
        "yellow": "#ffff00",
        "orange": "#ffa500",
    }

    if literal in _dict:
        return hex_to_rgb(_dict[literal])
    else:
        return (0, 0, 0)


def hex_to_rgb(hex):
    if hex and hex != "none":
        try:
            hex = hex.lstrip('#')
            hlen = len(hex)
            return tuple(int(hex[i:i + hlen // 3], 16) / 255.0 for i in range(0, hlen, hlen // 3))
        except Exception as e:
            logging.error(f"Could not convert hex [{hex}] to rgb ")
    return (0, 0, 0)


def rgb_literal(str):
    _v = str
    _v = _v.replace("rgb(", "")
    _v = _v.replace(")", "")
    _v = _v.split(',')
    _v = [float(i)/255.0 for i in _v]

    return _v

# TODO: Handle rgb literal


def convert_color(hex):
    c = (0, 0, 0)
    if 'rgb' in hex:
        c = rgb_literal(hex)
    elif hex.startswith('#'):
        c = hex_to_rgb(hex)
    else:
        c = literal_to_rgb(hex)
    return Gf.Vec3f(c[0], c[1], c[2])

# Take SVG Transform string and make xform ops


def convert_transform_attr(transform_attr, up_axis="Y"):
    # TODO: We should support making a matrix op and per component

    _output = Gf.Matrix4d(1.0)
    _translate_mat = Gf.Matrix4d(1.0)
    _rotate_mat = Gf.Matrix4d(1.0)

    translate_search = re.search(
        'translate\(.*?\)', transform_attr, re.IGNORECASE)
    rotate_search = re.search('rotate\(.*?\)', transform_attr, re.IGNORECASE)

    if rotate_search:
        _rotate = rotate_search.group(0).replace("rotate(", "")
        _rotate = _rotate.replace(")", "")

        if "," in _rotate:
            # TODO: Figure out what this means....
            _rotate = [-float(i) for i in _rotate.split(',')]
            _r = Gf.Rotation(Gf.Vec3d(0, 1, 0), _rotate[0])
            _rotate_mat = Gf.Matrix4d(1).SetRotate(_r)
        else:
            _rotate = -float(_rotate)
            _r = Gf.Rotation(Gf.Vec3d(0, 1, 0), _rotate)
            _rotate_mat = Gf.Matrix4d(1).SetRotate(_r)

    # TODO: Handle Scale
    # TODO: Handle multiple transforms
    if translate_search:
        _translate = translate_search.group(0).replace("translate(", "")
        _translate = _translate.replace(")", "")
        if "," in _translate:
            _translate = [float(i) for i in _translate.split(',')]
        elif " " in _translate:
            _translate = [float(i) for i in _translate.split(' ')]
        _v = convert_position(_translate[0], _translate[1], vec_class=Gf.Vec3d)
        _translate_mat = Gf.Matrix4d(1).SetTranslate(_v)

    _output = _rotate_mat * _translate_mat

    return _output


DEBUG = True


def area(p):
    return 0.5 * (sum(x0*y1 - x1*y0 for ((x0, y0), (x1, y1)) in segments(p)))


def segments(p):
    return zip(p, p[1:] + [p[0]])

# TODO: Check if actually clockwise based on -y coord


def _is_counter_clockwise(points):
    signedArea = 0
    for i, point in enumerate(points):
        x1 = point[0]
        y1 = point[1]
        if point[0] == points[-1][0] and point[1] == points[-1][1]:
            x2 = points[-1][0]
            y2 = points[-1][1]
        else:
            x2 = points[i+1][0]
            y2 = points[i+1][1]

        signedArea += (x1 * y2 - x2 * y1)

    return signedArea > 0


def path_to_mesh(svg_path, usd_points, usd_fvi, usd_fvc, x_offset=0, y_offset=0, scale_factor=1):

    # Array of arrays of points
    _polygons = svg_path.to_polygons()
    _num_polys = len(_polygons)

    # TODO: Put this in one of the other poly loops
    for i, _poly in enumerate(_polygons):
        for j, _point in enumerate(_poly):
            _polygons[i][j] = [(_point[0] + x_offset) * scale_factor,
                               (_point[1] + y_offset) * scale_factor]

    if _num_polys <= 0:
        return usd_points, usd_fvi, usd_fvc

    _polygon_windings = []

    for p in _polygons:
        _polygon_windings.append(_is_counter_clockwise(p))

    # - Convert single array of polys to array of 1 parent -> X children objects

    _poly_parents = []

    _children = []

    for _poly_idx, _poly in enumerate(_polygons):

        if _poly_idx in _children:
            continue
        _isCcw = _polygon_windings[_poly_idx]

        _comparrison_dir = _isCcw

        _p1_path = matplotlib.path.Path(_poly)

        _poly_storage = {
            "root": _poly,
            "children": []
        }

        # Seach all inside polygons and check if inside this polygon
        for _inside_poly_idx, _inside_poly in enumerate(_polygons):
            # Skip same
            if _poly_idx == _inside_poly_idx:
                continue
            # Skip outter
            if _polygon_windings[_inside_poly_idx] == _comparrison_dir:
                continue

            _p2_path = matplotlib.path.Path(_inside_poly)

            if _p1_path.contains_path(_p2_path):
                # This poly is inside parent
                _poly_storage["children"].append(_inside_poly)

                _children.append(_inside_poly_idx)

        _poly_parents.append(_poly_storage)

    # -

    _point_buffer = []
    _fvi_buffer = []
    _fvc_buffer = []

    for _poly_obj in _poly_parents:
        _polygons = [_poly_obj['root']] + _poly_obj['children']

        _closest_dist = -1
        _incoming_point_offset = len(usd_points)

        # array of tuples with indexes into original polygons
        # tuple in pattern (outside_idx, inside_idx)
        closest_pairs = [(-1, -1)] * (_num_polys - 1)
        _outside = _polygons[0]

        # loop over all inside polys
        for _inside_idx, _inside in enumerate(_polygons[1:]):
            _closest_dist = -1

            for _i_idx, _i_pos in enumerate(_inside):
                for _o_idx, _o_pos in enumerate(_outside):
                    _dist = (convert_position(
                        _i_pos[0], _i_pos[1]) - convert_position(_o_pos[0], _o_pos[1])).GetLength()
                    if _dist < _closest_dist or _closest_dist < 0:
                        _closest_dist = _dist
                        closest_pairs[_inside_idx] = (_o_idx, _i_idx)

        _combined_points = []
        _combined_fvi = []

        _idc_offset = 0

        for _polygon_idx, _polygon in enumerate(_polygons):
            _sub_points = [convert_position(_v[0], _v[1]) for _v in _polygon]
            # Assumes that incoming polygons are closed and duplicate end points
            _sub_points = _sub_points[:-1]
            _sub_num_points = len(_sub_points)

            _sub_fvi = [i for i in range(_sub_num_points)]

            if _polygon_idx == 0:
                # First polygon is outside, so added normally
                _combined_points += _sub_points
                _combined_fvi += _sub_fvi
            else:
                _adjusted_fvi = [i + _idc_offset for i in _sub_fvi]

                _pair = closest_pairs[_polygon_idx - 1]

                _combined_points += _sub_points

                # This is ugly
                _outside_insertion_pos = convert_position(
                    _polygons[0][_pair[0]][0], _polygons[0][_pair[0]][1])
                _inside_insertion_pos = convert_position(
                    _polygon[_pair[1]][0], _polygon[_pair[1]][1])

                _outside_insertion_idx = _combined_points.index(
                    _outside_insertion_pos)
                _inside_insertion_idx = _combined_points.index(
                    _inside_insertion_pos)

                _roll_idx = _adjusted_fvi.index(_inside_insertion_idx)
                _adjusted_fvi = _adjusted_fvi[_roll_idx:] + \
                    _adjusted_fvi[:_roll_idx]

                _insertion_idx = _combined_fvi.index(_outside_insertion_idx)
                _combined_fvi[_insertion_idx:_insertion_idx] = [
                    _outside_insertion_idx] + _adjusted_fvi + [_inside_insertion_idx]

            _idc_offset += _sub_num_points

        _fvi_buffer += [k + len(_point_buffer) +
                        _incoming_point_offset for k in _combined_fvi]
        _point_buffer += _combined_points
        _fvc_buffer += [len(_combined_fvi)]

    usd_points += _point_buffer
    usd_fvi += _fvi_buffer
    usd_fvc += _fvc_buffer

    return usd_points, usd_fvi, usd_fvc


def path_to_curve(svg_path, usd_points, usd_fvc, x_offset=0, y_offset=0):
    _polygons = svg_path.to_polygons()
    _num_polygons = len(_polygons)

    if _num_polygons <= 0:
        return usd_points, usd_fvc

    for pi, p in enumerate(_polygons):
        _points = [convert_position(v[0], v[1]) for v in p]

        # TODO: Should check if first and last are the same...
        # But most seem to be
        _points = _points[:-1]
        _num_points = len(_points)

        usd_points += _points

        usd_fvc += [_num_points]

    return usd_points, usd_fvc


def handle_xform_attrs(svg_element, usd_xform):

    # - Transform

    if 'transform' in svg_element.attrib:
        _transform = svg_element.attrib['transform']
        _matrix = convert_transform_attr(_transform)
        usd_xform.AddTransformOp().Set(_matrix)


def handle_geom_attrs(svg_element, usd_mesh):

    handle_xform_attrs(svg_element, usd_mesh)

    # - X, Y
    # TODO: Implement
    try:
        svg_x = float(svg_element.attrib['x'])
    except:
        svg_x = 0.0
    try:
        svg_y = float(svg_element.attrib['y'])
    except:
        svg_y = 0.0

    # - Colors

    svg_fill = "#FFF"
    if 'fill' in svg_element.attrib:
        svg_fill = svg_element.attrib['fill']

    if 'style' in svg_element.attrib:
        svg_style = svg_element.attrib['style']
        svg_style = svg_style.split(';')
        for style_el in svg_style:
            el_comp = style_el.split(':')
            if el_comp[0] == "fill":
                if el_comp[1] == "none":
                    return
                else:
                    svg_fill = el_comp[1]

    if "url(" in svg_fill:
        pattern_id = svg_fill.replace('url(#', '')
        pattern_id = pattern_id.replace(')', '')

        image_id = common.pattern_map[pattern_id]
        usd_material = common.image_map[image_id]

        binding = UsdShade.MaterialBindingAPI.Apply(usd_mesh.GetPrim())
        if binding:
            binding.Bind(usd_material)
    else:
        usd_colors = [convert_color(svg_fill)]

        usd_mesh.CreateDisplayColorPrimvar(
            UsdGeom.Tokens.constant).Set(usd_colors)
        # usd_mesh.SetDisplayColorInterpolation(UsdGeom.Tokens.constant)

    # - Normals

    usd_normals = [default_normal()]
    usd_mesh.CreateNormalsAttr().Set(usd_normals)
    usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.constant)

    # - Arbitrary attributes

    disallow_list = ["fill", "style", "x", "y",
                     "transform", "d", "x1", "x2", "y1", "y2", "points"]
    # These probably arent useful
    disallow_list += ["clip_path", "clip_path_id"]

    for _attr in svg_element.attrib:
        if _attr in disallow_list:
            continue
        _val = svg_element.attrib[_attr]

        _type = convert_type(_val)
        if _type:
            usd_mesh.CreatePrimvar(Tf.MakeValidIdentifier(
                _attr), _type, UsdGeom.Tokens.constant).Set(_val)

    return usd_mesh
