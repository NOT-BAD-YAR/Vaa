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
    
    # Automatically parse coordinates from model output
    screen_width, screen_height = pyautogui.size()
    center_x, center_y = None, None

    # Format 1: Explicit x and y labels, e.g. "(x: 1050, y: 20)" or "x=1050, y=20"
    match_xy = re.search(r"x\s*[:=]\s*([0-9.]+).*?y\s*[:=]\s*([0-9.]+)", output_text, re.IGNORECASE)
    if not match_xy:
        match_yx = re.search(r"y\s*[:=]\s*([0-9.]+).*?x\s*[:=]\s*([0-9.]+)", output_text, re.IGNORECASE)
        if match_yx:
            center_y, center_x = float(match_yx.group(1)), float(match_yx.group(2))
    else:
        center_x, center_y = float(match_xy.group(1)), float(match_xy.group(2))

    # Format 2: 4-value bounding box [ymin, xmin, ymax, xmax] or [x1, y1, x2, y2]
    if center_x is None or center_y is None:
        coords_match = re.search(r"\[?\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]?", output_text)
        if coords_match:
            c1, c2, c3, c4 = [float(x) for x in coords_match.groups()]
            if all(c <= 1.0 for c in (c1, c2, c3, c4)):
                c1, c2, c3, c4 = c1 * screen_height, c2 * screen_width, c3 * screen_height, c4 * screen_width
            elif all(c <= 1000.0 for c in (c1, c2, c3, c4)) and any(c < 1000 for c in (c1, c2, c3, c4)):
                c1, c2, c3, c4 = (c1/1000.0)*screen_height, (c2/1000.0)*screen_width, (c3/1000.0)*screen_height, (c4/1000.0)*screen_width
                
            ymin, xmin, ymax, xmax = min(c1, c3), min(c2, c4), max(c1, c3), max(c2, c4)
            center_x = (xmin + xmax) / 2.0
            center_y = (ymin + ymax) / 2.0

    # Format 3: Simple 2-value coordinate pair (x, y) or [x, y]
    if center_x is None or center_y is None:
        match_pair = re.search(r"[\(\[\s]*([0-9]+)\s*[,x\s]\s*([0-9]+)[\)\]\s]*", output_text)
        if match_pair:
            center_x, center_y = float(match_pair.group(1)), float(match_pair.group(2))

    if center_x is not None and center_y is not None:
        center_x = max(0, min(int(round(center_x)), screen_width - 1))
        center_y = max(0, min(int(round(center_y)), screen_height - 1))
        print(f"--> Target located! Moving mouse to click at ({center_x}, {center_y})...")
        pyautogui.moveTo(center_x, center_y, duration=0.5)
        pyautogui.click()
    
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