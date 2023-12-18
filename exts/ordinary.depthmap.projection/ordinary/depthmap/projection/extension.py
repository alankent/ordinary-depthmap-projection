from typing import List, Tuple, Callable, Dict
from functools import partial
import os
import math

import carb.settings
import carb.windowing
import omni.appwindow
from carb import log_warn, events

import omni.ext
import omni.ui as ui
#from omni.kit.window.file_importer import get_file_importer
from omni.kit.window.filepicker import FilePickerDialog, UI_READY_EVENT
from omni.kit.widget.filebrowser import FileBrowserItem

from pxr import Usd, UsdShade, UsdGeom, Sdf, Gf
import omni.usd

import numpy as np
from PIL import Image



DEFAULT_FILE_EXTENSION_TYPES = [
    ("*.png, *.jpg", "Image Files"),
    ("*.*", "All files"),
]


def default_filter_handler(filename: str, filter_postfix: str, filter_ext: str) -> bool:

    if not filename:
        return True

    # Show only files whose names end with: *<postfix>.<ext>
    if filter_ext:
        # split comma separated string into a list:
        filter_exts = filter_ext.split(",") if isinstance(filter_ext, str) else filter_ext
        filter_exts = [x.replace(" ", "") for x in filter_exts]
        filter_exts = [x for x in filter_exts if x]

        # check if the file extension matches anything in the list:
        if not (
            "*.*" in filter_exts or
            any(filename.endswith(f.replace("*", "")) for f in filter_exts)
        ):
            # match failed:
            return False

    if filter_postfix:
        # strip extension and check postfix:
        filename = os.path.splitext(filename)[0]
        return filename.endswith(filter_postfix)

    return True


def on_filter_item(filter_fn: Callable[[str], bool], dialog: FilePickerDialog, item: FileBrowserItem, show_only_folders: bool = False) -> bool:
    if item and not item.is_folder:
        # OM-96626: Add show_only_folders option to file importer
        if show_only_folders:
            return False
        if filter_fn:
            return filter_fn(item.path or '', dialog.get_file_postfix(), dialog.get_file_extension())
    return True


def _save_default_settings(default_settings: Dict):
    settings = carb.settings.get_settings()
    default_settings_path = settings.get_as_string("/exts/omni.kit.window.file_importer/appSettings")
    settings.set_string(f"{default_settings_path}/directory", default_settings['directory'] or "")


def on_import(import_fn: Callable[[str, str, List[str]], None], dialog: FilePickerDialog, filename: str, dirname: str, hide_window_on_import: bool = True):
    _save_default_settings({'directory': dirname})
    selections = dialog.get_current_selections() or []
    if hide_window_on_import:
        dialog.hide()

    if import_fn:
        import_fn(filename, dirname, selections=selections)



# Any class derived from `omni.ext.IExt` in top level module (defined in `python.modules` of `extension.toml`) will be
# instantiated when extension gets enabled and `on_startup(ext_id)` will be called. Later when extension gets disabled
# on_shutdown() is called.
class OrdinaryDepthmapProjectionExtension(omni.ext.IExt):

    # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # this extension is located on filesystem.
    def on_startup(self, ext_id):
        print("[ordinary.depthmap.projection] ordinary depthmap projection startup")

        self.stage = omni.usd.get_context().get_stage()

        self._window = ui.Window("Ordinary Depth Map Projection", width=300, height=300)
        with self._window.frame:
            with ui.VStack():
                with ui.HStack():

                    def on_texture_click():

                        def import_handler(filename, dirname, selections = []):
                            self.texture_filename = os.path.join(dirname, filename)
                            self.texture_label.text = self.texture_filename

                        self.texture_dialog = FilePickerDialog(
                            'Select texture file',
                            apply_button_label = 'Open',
                            click_apply_handler = import_handler,
                            file_extension_options = DEFAULT_FILE_EXTENSION_TYPES
                        )
                        self.texture_dialog.set_item_filter_fn(partial(on_filter_item, default_filter_handler, self.texture_dialog, show_only_folders=False))
                        self.texture_dialog.set_click_apply_handler(partial(on_import, import_handler, self.texture_dialog, hide_window_on_import=True))
                        #self.texture_dialog._widget.file_bar.enable_apply_button(enable=show_only_folders)
                        self.texture_dialog.show()
                        self.texture_dialog._widget.file_bar.focus_filename_input()

                    ui.Button("Select Texture File", width=150, clicked_fn=on_texture_click)

                    self.texture_filename = ''
                    self.texture_label = ui.Label(self.texture_filename)

                with ui.HStack():

                    def on_depthmap_click():

                        def import_handler(filename, dirname, selections = []):
                            self.depthmap_filename = os.path.join(dirname, filename)
                            self.depthmap_label.text = self.depthmap_filename

                        self.depthmap_dialog = FilePickerDialog(
                            'Select depthmap file',
                            apply_button_label = 'Open',
                            click_apply_handler = import_handler,
                            file_extension_options = DEFAULT_FILE_EXTENSION_TYPES
                        )
                        self.depthmap_dialog.set_item_filter_fn(partial(on_filter_item, default_filter_handler, self.depthmap_dialog, show_only_folders=False))
                        self.depthmap_dialog.set_click_apply_handler(partial(on_import, import_handler, self.depthmap_dialog, hide_window_on_import=True))
                        #self.depthmap_dialog._widget.file_bar.enable_apply_button(enable=show_only_folders)
                        self.depthmap_dialog.show()

                    ui.Button("Select Depth Map File", width=150, clicked_fn=on_depthmap_click)

                    self.depthmap_filename = ''
                    self.depthmap_label = ui.Label(self.depthmap_filename)

                with ui.HStack():

                    def on_generate_click():
                        self.generate_new_mesh()

                    ui.Button("Generate", clicked_fn=on_generate_click)

    def generate_new_mesh(self):
        print("GENERATE", self.texture_filename, self.depthmap_filename)

        # Create the mesh
        xform = UsdGeom.Xform.Define(self.stage, "/my_plane")
        mesh = UsdGeom.Mesh.Define(self.stage, xform.GetPath().AppendChild("mesh"))
        mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)

        texture_image = Image.open(self.texture_filename)
        texture_width, texture_height = texture_image.size
        mesh_width = texture_width // 16
        mesh_height = texture_height // 16

        depthmap_image = Image.open(self.depthmap_filename)
        # datatype is optional, but can be useful for type conversion
        depthmap_data = np.asarray(depthmap_image, dtype=np.uint8)
        depthmap_height, depthmap_width, depthmap_colors = depthmap_data.shape

        points = []
        normals = []
        st = []
        normal = (0, 1, 0)
        vertex_counts = []
        vertex_indicies = []

        def clamp(value, min_value, max_value):
            return max(min(int(value), max_value), min_value)

        for y in range(mesh_height + 1):
            for x in range(mesh_width + 1):
                dmx = clamp(x / mesh_width * depthmap_width, 0, depthmap_width - 1)
                dmy = clamp((mesh_height - y) / mesh_height * depthmap_height, 0, depthmap_height - 1)
                distance = depthmap_data[dmy, dmx, 0] / 256 * mesh_height
                points.append(Gf.Vec3f(x - mesh_width/2, y - mesh_height/2, distance))

        for y in range(mesh_height):
            for x in range(mesh_width):
                vertex_counts.append(3)
                vertex_indicies.append(y * (mesh_width + 1) + x) # LL
                vertex_indicies.append(y * (mesh_width + 1) + x + 1) # LR
                vertex_indicies.append((y + 1) * (mesh_width + 1) + x) # UL
                st.append((x / mesh_width, y / mesh_height)) # LL
                st.append(((x + 1) / mesh_width, y / mesh_height)) # LR
                st.append((x / mesh_width, (y + 1) / mesh_height)) # UL
                normals.append(normal)
                normals.append(normal)
                normals.append(normal)
                vertex_counts.append(3)
                vertex_indicies.append(y * (mesh_width + 1) + x + 1) # LR
                vertex_indicies.append((y + 1) * (mesh_width + 1) + x + 1) # UR
                vertex_indicies.append((y + 1) * (mesh_width + 1) + x) # UL
                st.append(((x + 1) / mesh_width, y / mesh_height)) # LR
                st.append(((x + 1) / mesh_width, (y + 1) / mesh_height)) # UR
                st.append((x / mesh_width, (y + 1) / mesh_height)) # UL
                normals.append(normal)
                normals.append(normal)
                normals.append(normal)

        mesh.CreatePointsAttr(points)
        mesh.CreateExtentAttr(UsdGeom.PointBased(mesh).ComputeExtent(mesh.GetPointsAttr().Get()))
        mesh.CreateFaceVertexCountsAttr(vertex_counts)
        mesh.CreateFaceVertexIndicesAttr(vertex_indicies)

        mesh.CreateNormalsAttr(normals)
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
        primvar_api = UsdGeom.PrimvarsAPI(mesh.GetPrim())
        primvar_api.CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying).Set(st)

        # Apply texture to the plane
        material = UsdShade.Material.Define(self.stage, xform.GetPath().AppendChild("material"))

        shader = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild("texture_shader"))
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((1.0, 1.0, 1.0))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

        diffuse_tx = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild("DiffuseColorTx"))
        diffuse_tx.CreateIdAttr('UsdUVTexture')
        diffuse_tx.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(self.texture_filename)
        diffuse_tx.CreateOutput('rgb', Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(diffuse_tx.ConnectableAPI(), 'rgb')
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

        #stInput = shader.CreateInput("st", Sdf.ValueTypeNames.TexCoord2fArray)

        # Create a texture and connect it to the shader's diffuse color
        #diffuseTexture = UsdShade.TextureInput(shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f))
        #diffuseTexture.SetTextureFile(texture_filename)
        #stInput.ConnectToSource(diffuseTexture.GetOutput())
        #material.CreateSurfaceOutput().ConnectToSource(shader.GetOutput("surface"))

        #shader.CreateIdAttr("UsdUVTexture")
        #shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(self.texture_filename)

        #st_input = material.CreateInput("st", Sdf.ValueTypeNames.TexCoord2fArray)
        #shader_output = shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

        #st_input.ConnectToSource(shader_output)

        #shader_connection = material.CreateShaderIdAttr().ConnectToSource(shader.GetIdAttr())

        material_binding = UsdShade.MaterialBindingAPI(mesh.GetPrim())
        material_binding.Bind(material)

    def on_shutdown(self):
        print("[ordinary.depthmap.projection] ordinary depthmap projection shutdown")
