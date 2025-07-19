bl_info = {
    "name": "AI Blender Assistant",
    "author": "Hanish",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > AI Assistant",
    "description": "Takes natural language and converts it to Blender Python",
    "category": "3D View",
}

import bpy
import re
from openai import OpenAI

# ----------- OpenRouter API Setup -----------
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="your_openrouter_api_key_here"  # Replace with your OpenRouter API key
)

def extract_code_block(text):
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else text.strip()

def get_scene_summary():
    summary = []
    for obj in bpy.context.scene.objects:
        summary.append(f"Name: {obj.name}, Type: {obj.type}, Location: {tuple(round(c, 2) for c in obj.location)}")
    return "\n".join(summary)

def get_step_by_step_thoughts(prompt):
    try:
        llama_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key="your_openrouter_api_key_here"  # Replace with your OpenRouter API key
        )
        response = llama_client.chat.completions.create(
            model="mistralai/mistral-small-3.1-24b-instruct:free",
            messages=[
                {"role": "system", "content": 'You are a technical assistant for Blender scripting. Break down the modeling task into clear, logical steps that directly correspond to Python operations in Blender. Each step should describe exactly what to do using Blender terminology (e.g., "Add a cube", "Scale it on the X axis by 2", "Apply a subdivision modifier"). Do not include any UI instructions or user-facing language. Do not mention Blender itself. Just list the modeling steps in sequence for an AI model to turn into code. Give me a clean output without any formatting'},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[API Error]: {e}")
        return f"# Error occurred: {e}"

def invoke_ai_logic(prompt):
    try:
        scene_info = get_scene_summary()
        prompt_with_context = f"Scene Overview:\n{scene_info}\n\nTask: {prompt}"

        completion = client.chat.completions.create(
            model="deepseek/deepseek-r1-0528:free",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes Python code for Blender. Modify or add to the scene without deleting existing objects."},
                {"role": "user", "content": prompt_with_context}
            ]
        )
        result = completion.choices[0].message.content
        print("[AI Response]:", result)
        code = extract_code_block(result)
        print("[Extracted Code]:", code)
        return code
    except Exception as e:
        print(f"[API Error]: {e}")
        return f"# Error occurred: {e}"
# -------------------------------------------

# ---------- UI Panel ----------
class AIBL_PT_panel(bpy.types.Panel):
    bl_label = "AI Assistant"
    bl_idname = "AIBL_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AI Assistant'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "ai_prompt")
        layout.prop(context.scene, "ai_mode")
        layout.operator("wm.generate_blender_code")

        if context.scene.ai_reasoning:
            layout.label(text="Step-by-Step Breakdown:")
            layout.prop(context.scene, "ai_reasoning", text="")
# -------------------------------

# ---------- Operators ----------
class AIBL_OT_generate(bpy.types.Operator):
    bl_label = "Generate"
    bl_idname = "wm.generate_blender_code"

    def execute(self, context):
        prompt = context.scene.ai_prompt
        mode = context.scene.ai_mode

        if mode == 'STEP_BY_STEP':
            thoughts = get_step_by_step_thoughts(prompt)
            context.scene.ai_reasoning = thoughts
            self.report({'INFO'}, "Step-by-step reasoning generated.")
            return {'FINISHED'}

        generated_code = invoke_ai_logic(prompt)

        try:
            exec(generated_code, globals())
            self.report({'INFO'}, "Script executed successfully.")
        except Exception as e:
            self.report({'ERROR'}, f"Execution failed: {e}")
            print(f"[ERROR] {e}")

        return {'FINISHED'}
# -------------------------------

# ---------- Registration ----------
def register():
    bpy.utils.register_class(AIBL_PT_panel)
    bpy.utils.register_class(AIBL_OT_generate)

    bpy.types.Scene.ai_prompt = bpy.props.StringProperty(
        name="Prompt", description="Enter your natural language instruction")

    bpy.types.Scene.ai_mode = bpy.props.EnumProperty(
        name="Mode",
        description="Choose AI generation mode",
        items=[
            ('DIRECT', "Direct", "Generate code directly using DeepSeek"),
            ('STEP_BY_STEP', "Step-by-Step", "Use LLaMA for logical modeling steps")
        ],
        default='DIRECT'
    )

    bpy.types.Scene.ai_reasoning = bpy.props.StringProperty(
        name="Reasoning Output",
        description="Step-by-step breakdown from AI",
        default="",
        options={'TEXTEDIT_UPDATE'},
        subtype='NONE'
    )

def unregister():
    bpy.utils.unregister_class(AIBL_PT_panel)
    bpy.utils.unregister_class(AIBL_OT_generate)

    del bpy.types.Scene.ai_prompt
    del bpy.types.Scene.ai_mode
    del bpy.types.Scene.ai_reasoning
# ----------------------------------

if __name__ == "__main__":
    register()