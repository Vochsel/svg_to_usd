import base64

from pxr import Usd, UsdShade, Sdf

from .. import utils, conversion_context


def convert(usd_stage, prim_path, svg_image):
    if '{http://www.w3.org/1999/xlink}href' not in svg_image.attrib:
        # No image data
        return

    img_id = svg_image.attrib['id']
    img_name = 'img_{}'.format(img_id) 
    if 'data-name' in svg_image.attrib:
        img_name = svg_image.attrib['data-name']

    img_path = conversion_context['texture_directory'] + "/" + img_name

    img_data = svg_image.attrib['{http://www.w3.org/1999/xlink}href']
    img_data = img_data.replace('data:image/png;base64,', '')
    

    # or, more concisely using with statement
    with open(img_path, "wb") as fh:
        fh.write(base64.b64decode(img_data))

    material = UsdShade.Material.Define(usd_stage, prim_path)

    preview_surface = UsdShade.Shader.Define(
        usd_stage, prim_path.AppendChild("preview_surface"))
    preview_surface.CreateIdAttr().Set("UsdPreviewSurface")

    texture = UsdShade.Shader.Define(usd_stage, prim_path.AppendChild("texture"))
    texture.CreateIdAttr().Set("UsdUVTexture")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(img_path)
    texture.CreateOutput('rgb', Sdf.ValueTypeNames.Float3)
    texture.CreateOutput('a', Sdf.ValueTypeNames.Float)

    uv_reader = UsdShade.Shader.Define(usd_stage, prim_path.AppendChild("uv_reader"))
    uv_reader.CreateIdAttr().Set("UsdPrimvarReader_float2")
    uv_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    texture.CreateOutput('result', Sdf.ValueTypeNames.Float2)
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        uv_reader.ConnectableAPI(), 'result')

    preview_surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.ConnectableAPI(), 'rgb')
    preview_surface.CreateInput("opacity", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.ConnectableAPI(), 'a')

    material.CreateSurfaceOutput().ConnectToSource(
        preview_surface.ConnectableAPI(), "surface")

    return material
