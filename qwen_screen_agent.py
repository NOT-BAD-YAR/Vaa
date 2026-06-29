import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import torch

# Compatibility fix for torchao 0.17+ when running on PyTorch < 2.7
if not hasattr(torch.utils._pytree, "register_constant") and hasattr(torch.utils._pytree, "register_pytree_node"):
    torch.utils._pytree.register_constant = lambda cls: torch.utils._pytree.register_pytree_node(cls, lambda x: ([], x), lambda x, _: x) or cls

import pyautogui
import re
from PIL import Image
from dotenv import load_dotenv
from transformers import AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info

load_dotenv()


MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"

print("Loading Qwen Processor and Model. This may take a moment...")
processor = AutoProcessor.from_pretrained(MODEL_NAME)
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_NAME,
    torch_dtype="auto",
    device_map="auto" # GPU acceleration enabled!
)
print("Qwen Model loaded successfully and ready to act!")

def act_on_screen(instruction: str):
    print("Taking screenshot of the current desktop...")
    screenshot = pyautogui.screenshot()
    
    # Qwen2.5-VL requires dimensions to be a multiple of 28.
    # We resize it slightly to prevent the patch matching errors on CPU.
    width, height = screenshot.size
    new_width = max(28, round(width / 28) * 28)
    new_height = max(28, round(height / 28) * 28)
    screenshot = screenshot.resize((new_width, new_height))
    
    # We ask the model to provide actionable coordinates or a response.
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image", 
                    "image": screenshot,
                    "resized_height": 896,
                    "resized_width": 896
                },
                {
                    "type": "text", 
                    "text": f"You are a helpful Windows UI assistant. Based on this screenshot, the user wants to: '{instruction}'. If you need to click on something, provide its exact bounding box or point coordinates. Be concise."
                }
            ]
        }
    ]
    
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt"
    ).to(model.device)
    
    print("Thinking...")
    generated_ids = model.generate(**inputs, max_new_tokens=128) # pyright: ignore[reportAttributeAccessIssue]
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    
    print(f"\n[Qwen Output]: {output_text}\n")
    
    # In a fully fleshed out agent, you would parse the specific coordinate format 
    # (e.g. <|box_start|>(x1,y1),(x2,y2)<|box_end|>) from output_text and use 
    # pyautogui.click(x, y) here!
    
if __name__ == "__main__":
    print("Welcome to the Qwen Screen Agent!")
    while True:
        user_input = input("\nEnter a command for the screen (or 'q' to quit): ").strip()
        if user_input.lower() == 'q':
            print("Exiting.")
            break
        if user_input:
            try:
                act_on_screen(user_input)
            except Exception as e:
                print(f"An error occurred: {e}")
