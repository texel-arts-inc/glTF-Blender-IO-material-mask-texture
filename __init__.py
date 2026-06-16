import bpy
from io_scene_gltf2.blender.exp.material.image import gather_image
from io_scene_gltf2.blender.exp.material.image import get_gltf_image_from_blender_image
from io_scene_gltf2.blender.exp.material.search_node_tree import NodeSocket

bl_info = {
    "name": "glTF TXA_material_mask_texture IO",
    "author": "Yash Varma",
    "description": "Addon for glTF TXA_material_mask_texture extension",
    "blender": (3, 3, 0),
    "version": (0, 0, 1),
    "location": "",
    "wiki_url": "",
    "tracker_url": "",
    "support": "COMMUNITY",
    "warning": "",
    "category": "Generic"
}

gltf_node_name = "glTF Mask Material Output"
txa_extension_name = "TXA_material_mask_texture"
txa_node_extension_name = "TXA_node_property_overrides"

def create_settings_group(name):
    gltf_node_group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    gltf_node_group.interface.new_socket("Mask Texture", socket_type="NodeSocketFloat")

    maskFactor = gltf_node_group.interface.new_socket("Mask Factor", socket_type="NodeSocketFloat")
    maskFactor.default_value = 1.0

    maskEnabled = gltf_node_group.interface.new_socket("Mask Enabled", socket_type="NodeSocketBool")
    maskEnabled.default_value = False

    paintedColor = gltf_node_group.interface.new_socket("Painted Color", socket_type="NodeSocketColor")
    paintedColor.default_value = (1.0, 1.0, 1.0, 1.0)

    gltf_node_group.nodes.new('NodeGroupOutput')
    gltf_node_group_input = gltf_node_group.nodes.new('NodeGroupInput')
    gltf_node_group_input.location = -200, 0

    return gltf_node_group


class NODE_OT_MASK_TEXTURE(bpy.types.Operator):
    bl_idname = "node.gltf_mask_texture_node_operator"
    bl_label = gltf_node_name
    bl_description = "Add a node to the active tree for glTF mask material export"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        condition = (
            space is not None
            and space.type == "NODE_EDITOR"
            and context.object and context.object.active_material
            and context.object.active_material.use_nodes is True
            and bpy.context.preferences.addons['io_scene_gltf2'].preferences.settings_node_ui is True
        )
        return condition

    def execute(self, context):
        material = context.object.active_material

        if gltf_node_name not in bpy.data.node_groups:
            create_settings_group(gltf_node_name)

        base_group = bpy.data.node_groups[gltf_node_name]

        unique_group_name = f"{gltf_node_name}_{material.name}"
        group_copy = base_group.copy()
        group_copy.name = unique_group_name

        node_tree = material.node_tree
        new_node = node_tree.nodes.new("ShaderNodeGroup")
        new_node.node_tree = group_copy
        new_node.label = gltf_node_name

        return {"FINISHED"}


def add_gltf_mask_texture_to_menu(self, context):
    if bpy.context.preferences.addons['io_scene_gltf2'].preferences.settings_node_ui is True:
        self.layout.operator("node.gltf_mask_texture_node_operator")


def find_image_from_socket(socket, max_depth=10):
    current_socket = socket
    depth = 0

    while current_socket and current_socket.is_linked and depth < max_depth:
        from_socket = current_socket.links[0].from_socket
        from_node = from_socket.node

        if from_node.type == 'TEX_IMAGE':
            return from_node.image

        if hasattr(from_node, 'inputs') and len(from_node.inputs) > 0:
            current_socket = from_node.inputs[0]
        else:
            break

        depth += 1

    return None


def strip_png(name: str) -> str:
    if name.lower().endswith(".png"):
        return name[:-4]
    return name


def find_group_node(material):
    """Find the glTF mask group node on a material, or return None."""
    if not material or not material.use_nodes:
        return None
    for node in material.node_tree.nodes:
        if node.type == "GROUP" and node.node_tree and gltf_node_name in node.node_tree.name:
            return node
    return None


class glTF2ExportUserExtension:
    def __init__(self):
        from io_scene_gltf2.io.com.gltf2_io_extensions import Extension
        self.Extension = Extension

    def gather_material_hook(self, gltf2_object, blender_material, export_settings):
        if not blender_material or not blender_material.use_nodes:
            return None

        group_node = find_group_node(blender_material)
        if not group_node:
            return None

        mask_texture_socket = group_node.inputs.get("Mask Texture")
        if not mask_texture_socket or not mask_texture_socket.is_linked:
            return None

        mask_texture_image = find_image_from_socket(mask_texture_socket)
        if not mask_texture_image:
            return None

        gltf2_object.mask_texture_image_name = mask_texture_image.name

        mask_factor_socket = group_node.inputs.get("Mask Factor")
        gltf2_object.mask_factor = (
            mask_factor_socket.default_value
            if mask_factor_socket and not mask_factor_socket.is_linked
            else 1.0
        )

        mask_enabled_socket = group_node.inputs.get("Mask Enabled")
        gltf2_object.mask_enabled = (
            mask_enabled_socket.default_value
            if mask_enabled_socket and not mask_enabled_socket.is_linked
            else False
        )

        painted_color_socket = group_node.inputs.get("Painted Color")
        if painted_color_socket and not painted_color_socket.is_linked:
            gltf2_object.painted_color = list(painted_color_socket.default_value[:3])
        else:
            gltf2_object.painted_color = None

    def gather_node_hook(self, gltf2_object, blender_object, export_settings):
        if not blender_object or not hasattr(blender_object, 'material_slots'):
            return

        pending_overrides = []

        for slot in blender_object.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue

            group_node = find_group_node(mat)
            if not group_node:
                continue

            painted_color_socket = group_node.inputs.get("Painted Color")
            if not painted_color_socket or painted_color_socket.is_linked:
                continue

            painted_color = list(painted_color_socket.default_value[:3])

            pending_overrides.append({
                "material_name": mat.name,
                "painted_color": painted_color
            })

        if not pending_overrides:
            return

        gltf2_object.pending_painted_overrides = pending_overrides

    def gather_gltf_extensions_hook(self, gltf_data, export_settings):
        mesh_instanced_materials_used = False
        node_overrides_used = False

        for mat in gltf_data.materials:
            if not hasattr(mat, "mask_texture_image_name"):
                continue

            mask_texture_image_name = mat.mask_texture_image_name
            mesh_instanced_materials_used = True
            image_index = None

            for i, image in enumerate(gltf_data.images):
                if strip_png(image.name) == strip_png(mask_texture_image_name):
                    image_index = i
                    break

            if image_index is None:
                continue

            texture_index = None
            for i, texture in enumerate(gltf_data.textures):
                if texture.source == image_index:
                    texture_index = i
                    break

            if texture_index is None:
                continue

            mask_factor = mat.mask_factor if hasattr(mat, "mask_factor") else 1.0
            mask_enabled = mat.mask_enabled if hasattr(mat, "mask_enabled") else False
            painted_color = mat.painted_color if hasattr(mat, "painted_color") else None

            extension_data = {
                "maskTexture": {
                    "index": texture_index,
                },
                "maskAlphaFactor": mask_factor,
                "maskEnabled": mask_enabled,
            }

            if painted_color is not None:
                extension_data["paintedColor"] = [1.0, 1.0, 1.0]

            mat.extensions = mat.extensions or {}
            mat.extensions[txa_extension_name] = extension_data

        # ---- Resolve node overrides using global material index ----
        material_index_map = {}
        for i, mat in enumerate(gltf_data.materials):
            material_index_map[mat.name] = i

        for node in gltf_data.nodes:
            if not hasattr(node, 'pending_painted_overrides'):
                continue

            overrides = []
            for pending in node.pending_painted_overrides:
                mat_index = material_index_map.get(pending["material_name"])
                if mat_index is None:
                    continue
                overrides.append({
                    "Material": mat_index,
                    "Enabled": True,
                    "Overrides": {
                        "paintedColor": pending["painted_color"]
                    }
                })

            if overrides:
                node.extensions = node.extensions or {}
                node.extensions[txa_node_extension_name] = {"overrides": overrides}
                node_overrides_used = True
        # ---- End node overrides ----

        if mesh_instanced_materials_used:
            if not gltf_data.extensions_used:
                gltf_data.extensions_used = []
            if txa_extension_name not in gltf_data.extensions_used:
                gltf_data.extensions_used.append(txa_extension_name)

        if node_overrides_used:
            if not gltf_data.extensions_used:
                gltf_data.extensions_used = []
            if txa_node_extension_name not in gltf_data.extensions_used:
                gltf_data.extensions_used.append(txa_node_extension_name)


def register():
    bpy.utils.register_class(NODE_OT_MASK_TEXTURE)
    bpy.types.NODE_MT_category_shader_output.append(add_gltf_mask_texture_to_menu)


def unregister():
    bpy.utils.unregister_class(NODE_OT_MASK_TEXTURE)
