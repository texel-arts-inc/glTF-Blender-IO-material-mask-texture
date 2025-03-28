import bpy

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

def create_settings_group(name):
    gltf_node_group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    gltf_node_group.interface.new_socket("Mask Texture", socket_type="NodeSocketFloat")

    maskFactor = gltf_node_group.interface.new_socket("Mask Factor", socket_type="NodeSocketFloat", )
    maskFactor.default_value = 1.0

    gltf_node_group.nodes.new('NodeGroupOutput')
    gltf_node_group_input = gltf_node_group.nodes.new('NodeGroupInput')
    gltf_node_group_input.location = -200, 0

    return gltf_node_group

# Add custom output node to shader panel
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
        if gltf_node_name in bpy.data.node_groups:
            group = bpy.data.node_groups[gltf_node_name]
        else:
            group = create_settings_group(gltf_node_name)

        node_tree = context.object.active_material.node_tree
        new_node = node_tree.nodes.new("ShaderNodeGroup")
        new_node.node_tree = bpy.data.node_groups[gltf_node_name]
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

# Export extension usage and extension data
class glTF2ExportUserExtension:
    def __init__(self):
        from io_scene_gltf2.io.com.gltf2_io_extensions import Extension

        self.Extension = Extension

    def gather_material_hook(self, gltf2_object, blender_material, export_settings):
        if not blender_material or not blender_material.use_nodes:
            return None

        node_tree = blender_material.node_tree
        group_node = None

        for node in node_tree.nodes:
            if node.type == "GROUP" and node.node_tree and node.node_tree.name == gltf_node_name:
                group_node = node
                break

        if not group_node:
            return None

        mask_texture_socket = group_node.inputs.get("Mask Texture")

        if not mask_texture_socket or not mask_texture_socket.is_linked:
            return None

        mask_texture_image = find_image_from_socket(mask_texture_socket)

        if not mask_texture_image:
            return None

        gltf2_object.mask_texture_image_name = mask_texture_image.name

        # TODO: Add retrieval of maskFactor here. For now, it defaults to 1.0 within the extension

    def gather_gltf_extensions_hook(self, gltf_data, export_settings):
        mesh_instanced_materials_used = False

        for mat in gltf_data.materials:
            if not hasattr(mat, "mask_texture_image_name"):
                continue

            mask_texture_image_name = mat.mask_texture_image_name
            mesh_instanced_materials_used = True 
            image_index = None

            for i, image in enumerate(gltf_data.images):
                if image.name == mask_texture_image_name:
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

            extension_data = {
                "maskTexture": {
                    "index": texture_index,
                    "maskFactor": 1.0
                }
            }

            mat.extensions = mat.extensions or {}
            mat.extensions[txa_extension_name] = extension_data

        if mesh_instanced_materials_used:
            if not gltf_data.extensions_used:
                gltf_data.extensions_used = []
            if txa_extension_name not in gltf_data.extensions_used:
                gltf_data.extensions_used.append(txa_extension_name)

def register():
    bpy.utils.register_class(NODE_OT_MASK_TEXTURE)
    bpy.types.NODE_MT_category_shader_output.append(add_gltf_mask_texture_to_menu)

def unregister():
    bpy.utils.register_class(NODE_OT_MASK_TEXTURE)
