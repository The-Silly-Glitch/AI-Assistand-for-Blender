bl_info = {
    "name": "AI Texture Generator",
    "author": "Hanish + ChatGPT",
    "version": (1, 3),
    "blender": (3, 0, 0),
    "location": "Shader Editor > Sidebar > AI Texture",
    "description": "Generates textures and modifies material nodes using AI",
    "category": "Material",
}

import bpy
import requests
import tempfile
import os
import textwrap
import re
from openai import OpenAI

# === API KEYS ===
OPENROUTER_API_KEY = "your_openrouter_api_key_here"
STABILITY_API_KEY = "your_stability_api_key_here"  # Optional if you want to hardcode it

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# === Utility: Collect Shader Node Info ===
def collect_shader_nodes():
    obj = bpy.context.active_object
    if not obj or not obj.active_material or not obj.active_material.use_nodes:
        return "No valid material with nodes found."

    node_tree = obj.active_material.node_tree
    node_info = ""

    for node in node_tree.nodes:
        node_info += f"\n--- Node: {node.name} ---\n"
        node_info += f"Type: {node.type}, Label: {node.label}, Location: {node.location}\n"

        if hasattr(node, "inputs"):
            for input_socket in node.inputs:
                if input_socket.name and input_socket.enabled:
                    value = None
                    if input_socket.is_linked:
                        value = "Linked"
                    elif hasattr(input_socket, 'default_value'):
                        value = input_socket.default_value
                        if isinstance(value, (list, tuple)) and len(value) > 3:
                            value = tuple(round(v, 3) for v in value[:4])
                        elif isinstance(value, float):
                            value = round(value, 3)
                    node_info += f"  Input: {input_socket.name} = {value}\n"
    return node_info

# === Utility: Extract Clean Code from AI ===
def extract_python_code(text):
    code_blocks = re.findall(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    return code_blocks[0].strip() if code_blocks else text.strip()

# === Send Prompt + Node Info to DeepSeek ===
def get_adjustment_script(prompt):
    node_details = collect_shader_nodes()
    try:
        completion = client.chat.completions.create(
            model="deepseek/deepseek-r1-0528:free",
            messages=[
                {
                    "role": "user",
                    "content": f"""
You are an expert in Blender scripting. Given this shader node info:

{node_details}

And this instruction:

{prompt}

Generate Python code that uses bpy to modify the active material's nodes.

Constraints:
- Modify existing nodes only (e.g., change Roughness, Metallic, Base Color).
- Do not create new materials.
- Access nodes with: node_tree = obj.active_material.node_tree
- Output only executable Python code. No markdown, no explanation.
                    """
                }
            ]
        )
        return extract_python_code(completion.choices[0].message.content)
    except Exception as e:
        print(f"[Script Generation Error]: {e}")
        return "# Error generating script"

# === Generate Texture Image from Prompt ===
def generate_texture_image(prompt, api_key):
    try:
        response = requests.post(
            "https://api.stability.ai/v2beta/stable-image/generate/sd3",
            headers={
                "authorization": f"Bearer {api_key}",
                "accept": "image/*"
            },
            files={"none": ''},
            data={
                "prompt": prompt,
                "output_format": "jpeg",
            },
        )
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg") as tmp:
                tmp.write(response.content)
                return tmp.name
        else:
            raise Exception(str(response.json()))
    except Exception as e:
        print(f"[Error generating texture]: {e}")
        return None

# === UI Panel ===
class AITX_PT_panel(bpy.types.Panel):
    bl_label = "AI Texture Generator"
    bl_idname = "AITX_PT_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'AI Texture'

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ShaderNodeTree'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "texture_prompt")
        layout.prop(context.scene, "stability_api_key")
        layout.operator("wm.aitx_generate_material")
        layout.operator("wm.aitx_apply_to_object")
        layout.separator()
        layout.prop(context.scene, "adjust_prompt")
        layout.operator("wm.aitx_adjust_material")

# === Operator: Generate Material ===
class AITX_OT_generate_material(bpy.types.Operator):
    bl_label = "Generate Material"
    bl_idname = "wm.aitx_generate_material"

    def execute(self, context):
        prompt = context.scene.texture_prompt
        api_key = context.scene.stability_api_key or STABILITY_API_KEY
        image_path = generate_texture_image(prompt, api_key)

        if not image_path:
            self.report({'ERROR'}, "Failed to generate image.")
            return {'CANCELLED'}

        image = bpy.data.images.load(image_path)
        mat = bpy.data.materials.new(name="AI_Generated_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        bsdf = nodes.get("Principled BSDF")
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image
        links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])

        context.scene.generated_material_name = mat.name
        self.report({'INFO'}, f"Material '{mat.name}' created")
        return {'FINISHED'}

# === Operator: Apply to Object ===
class AITX_OT_apply_to_object(bpy.types.Operator):
    bl_label = "Apply to Selected Object"
    bl_idname = "wm.aitx_apply_to_object"

    def execute(self, context):
        mat_name = context.scene.generated_material_name
        if not mat_name or mat_name not in bpy.data.materials:
            self.report({'ERROR'}, "No valid generated material found")
            return {'CANCELLED'}

        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No mesh object selected")
            return {'CANCELLED'}

        mat = bpy.data.materials[mat_name]
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat

        self.report({'INFO'}, f"Applied '{mat.name}' to selected object")
        return {'FINISHED'}

# === Operator: Adjust Material with AI ===
class AITX_OT_adjust_material(bpy.types.Operator):
    bl_label = "Adjust Material with AI"
    bl_idname = "wm.aitx_adjust_material"

    def execute(self, context):
        prompt = context.scene.adjust_prompt
        script = get_adjustment_script(prompt)

        try:
            print("=== AI Generated Code ===")
            print(script)
            exec(textwrap.dedent(script), {'bpy': bpy, 'obj': bpy.context.active_object})
            self.report({'INFO'}, "Material adjusted with AI.")
        except Exception as e:
            print(f"[Execution Error]: {e}")
            self.report({'ERROR'}, f"Script execution failed: {e}")
        return {'FINISHED'}

# === Registration ===
classes = (
    AITX_PT_panel,
    AITX_OT_generate_material,
    AITX_OT_apply_to_object,
    AITX_OT_adjust_material,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.texture_prompt = bpy.props.StringProperty(name="Texture Prompt")
    bpy.types.Scene.stability_api_key = bpy.props.StringProperty(name="Stability API Key", subtype='PASSWORD')
    bpy.types.Scene.generated_material_name = bpy.props.StringProperty(name="Generated Material")
    bpy.types.Scene.adjust_prompt = bpy.props.StringProperty(name="Adjust Prompt")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.texture_prompt
    del bpy.types.Scene.stability_api_key
    del bpy.types.Scene.generated_material_name
    del bpy.types.Scene.adjust_prompt

if __name__ == "__main__":
    register()
