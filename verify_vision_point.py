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
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from transformers import AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info

load_dotenv()

MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"

print("Loading Qwen Processor and Vision Model for Verification...")
processor = AutoProcessor.from_pretrained(MODEL_NAME)
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_NAME,
    torch_dtype="auto",
    device_map="auto"
)
print("✅ Qwen Model loaded successfully!")

def verify_vision_target(instruction: str, output_path: str = "media/verified_point.png"):
    os.makedirs("media", exist_ok=True)
    print(f"\n📸 Capturing screenshot of current screen...")
    screenshot = pyautogui.screenshot()
    orig_width, orig_height = screenshot.size
    
    # Qwen2.5-VL requires dimensions to be a multiple of 28
    new_width = max(28, round(orig_width / 28) * 28)
    new_height = max(28, round(orig_height / 28) * 28)
    resized_screenshot = screenshot.resize((new_width, new_height))
    
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image", 
                    "image": resized_screenshot
                },
                {
                    "type": "text", 
                    "text": f"You are a helpful Windows GUI agent. Locate the following element: '{instruction}'. Return only its bounding box [ymin, xmin, ymax, xmax] or center coordinates (x, y). Be concise."
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
    
    print(f"🤖 Analyzing screen for: '{instruction}'...")
    generated_ids = model.generate(**inputs, max_new_tokens=128) # pyright: ignore[reportAttributeAccessIssue]
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0].strip()
    
    print(f"\n[Qwen Response]: {output_text}\n")
    
    # Extract coordinates mapping to original screen resolution
    screen_width, screen_height = orig_width, orig_height
    center_x, center_y = None, None

    # Format 1: Explicit x and y labels, e.g. "x: 1050, y: 20"
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

    # Format 3: Simple 2-value coordinate pair (x, y)
    if center_x is None or center_y is None:
        match_pair = re.search(r"[\(\[\s]*([0-9]+)\s*[,x\s]\s*([0-9]+)[\)\]\s]*", output_text)
        if match_pair:
            center_x, center_y = float(match_pair.group(1)), float(match_pair.group(2))

    if center_x is None or center_y is None:
        print("❌ Could not extract numeric coordinates from model output.")
        return False, None

    # Prevent out-of-bounds cursor movements / drawing
    center_x = max(0, min(int(round(center_x)), orig_width - 1))
    center_y = max(0, min(int(round(center_y)), orig_height - 1))
    print(f"🎯 Resolved Target Coordinates: X={center_x}, Y={center_y}")
    
    # Visual Verification: Paint Large, High-Contrast Bullseye Marker on Original Screenshot
    draw = ImageDraw.Draw(screenshot)
    
    # 1. White outer contrast glow ring (Radius 70px)
    r1 = 70
    draw.ellipse([(center_x - r1, center_y - r1), (center_x + r1, center_y + r1)], outline="#FFFFFF", width=8)
    
    # 2. Main Neon Hot Pink Target Ring (Radius 66px)
    r2 = 66
    draw.ellipse([(center_x - r2, center_y - r2), (center_x + r2, center_y + r2)], outline="#FF007F", width=8)
    
    # 3. Inner Hot Pink Ring (Radius 36px)
    r3 = 36
    draw.ellipse([(center_x - r3, center_y - r3), (center_x + r3, center_y + r3)], outline="#FF007F", width=6)
    
    # 4. Massive Solid Center Point / Dot (Radius 16px)
    dot_r = 16
    draw.ellipse([(center_x - dot_r, center_y - dot_r), (center_x + dot_r, center_y + dot_r)], fill="#FF007F", outline="#FFFFFF", width=3)
    
    # 5. Long Prominent Crosshairs (extending 110px out)
    ch_in = 22
    ch_out = 110
    draw.line([(center_x - ch_out, center_y), (center_x - ch_in, center_y)], fill="#FF007F", width=6)
    draw.line([(center_x + ch_in, center_y), (center_x + ch_out, center_y)], fill="#FF007F", width=6)
    draw.line([(center_x, center_y - ch_out), (center_x, center_y - ch_in)], fill="#FF007F", width=6)
    draw.line([(center_x, center_y + ch_in), (center_x, center_y + ch_out)], fill="#FF007F", width=6)

    screenshot.save(output_path)
    print(f"🎨 Large neon pink verification bullseye painted at ({center_x}, {center_y})!")
    print(f"💾 Saved verified screenshot to: {os.path.abspath(output_path)}")
    
    # Auto-open the image so the human can immediately view and verify it
    try:
        os.startfile(os.path.abspath(output_path))
        print("🖼️ Opened verified image for human inspection!")
    except Exception as e:
        print(f"Note: Could not auto-open image ({e})")
        
    return True, (center_x, center_y)

def hierarchical_locate_and_verify(instruction: str, output_path: str = "media/verified_hierarchical.png"):
    """
    Two-Pass Hierarchical Crop Localization:
    Pass 1: Macro search for the broad UI section / bounding box.
    Pass 2: Micro precision grounding inside cropped high-resolution image.
    """
    os.makedirs("media", exist_ok=True)
    print(f"\n📸 [Pass 1] Capturing full screen for macro region search...")
    screenshot = pyautogui.screenshot()
    orig_width, orig_height = screenshot.size
    
    messages_p1 = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": screenshot},
                {"type": "text", "text": f"Locate the general UI region or section containing: '{instruction}'. Return only a bounding box [ymin, xmin, ymax, xmax]."}
            ]
        }
    ]
    text_p1 = processor.apply_chat_template(messages_p1, tokenize=False, add_generation_prompt=True)
    img_in_p1, vid_in_p1 = process_vision_info(messages_p1)
    inputs_p1 = processor(text=[text_p1], images=img_in_p1, videos=vid_in_p1, padding=True, return_tensors="pt").to(model.device)
    
    gen_ids_p1 = model.generate(**inputs_p1, max_new_tokens=128) # pyright: ignore[reportAttributeAccessIssue]
    out_p1 = processor.batch_decode([out[len(inp):] for inp, out in zip(inputs_p1.input_ids, gen_ids_p1)], skip_special_tokens=True)[0].strip()
    print(f"🤖 [Pass 1 Macro Output]: {out_p1}")
    
    coords_match = re.search(r"\[?\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]?", out_p1)
    if not coords_match:
        print("⚠️ Pass 1 could not resolve macro region bounding box. Falling back to single-pass...")
        return verify_vision_target(instruction, output_path)
        
    c1, c2, c3, c4 = [float(x) for x in coords_match.groups()]
    if all(c <= 1.0 for c in (c1, c2, c3, c4)):
        c1, c2, c3, c4 = c1 * orig_height, c2 * orig_width, c3 * orig_height, c4 * orig_width
    elif all(c <= 1000.0 for c in (c1, c2, c3, c4)) and any(c < 1000 for c in (c1, c2, c3, c4)):
        c1, c2, c3, c4 = (c1/1000.0)*orig_height, (c2/1000.0)*orig_width, (c3/1000.0)*orig_height, (c4/1000.0)*orig_width
        
    if max(c1, c3) > orig_height and max(c2, c4) <= orig_height:
        # Detected [xmin, ymin, xmax, ymax] order
        xmin, ymin, xmax, ymax = min(c1, c3), min(c2, c4), max(c1, c3), max(c2, c4)
    else:
        ymin, xmin, ymax, xmax = min(c1, c3), min(c2, c4), max(c1, c3), max(c2, c4)
        
    pad = 60
    crop_left = max(0, min(int(xmin - pad), orig_width - 20))
    crop_right = max(crop_left + 10, min(int(xmax + pad), orig_width))
    crop_top = max(0, min(int(ymin - pad), orig_height - 20))
    crop_bottom = max(crop_top + 10, min(int(ymax + pad), orig_height))
    
    print(f"✂️ [Pass 2] Cropping high-resolution region [{crop_left}, {crop_top}, {crop_right}, {crop_bottom}]...")
    cropped_img = screenshot.crop((crop_left, crop_top, crop_right, crop_bottom))
    crop_w, crop_h = cropped_img.size
    
    messages_p2 = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": cropped_img},
                {"type": "text", "text": f"Within this zoomed-in UI section, find the exact element: '{instruction}'. Return only its bounding box or center coordinates (x, y)."}
            ]
        }
    ]
    text_p2 = processor.apply_chat_template(messages_p2, tokenize=False, add_generation_prompt=True)
    img_in_p2, vid_in_p2 = process_vision_info(messages_p2)
    inputs_p2 = processor(text=[text_p2], images=img_in_p2, videos=vid_in_p2, padding=True, return_tensors="pt").to(model.device)
    
    gen_ids_p2 = model.generate(**inputs_p2, max_new_tokens=128) # pyright: ignore[reportAttributeAccessIssue]
    out_p2 = processor.batch_decode([out[len(inp):] for inp, out in zip(inputs_p2.input_ids, gen_ids_p2)], skip_special_tokens=True)[0].strip()
    print(f"🔍 [Pass 2 Micro Output]: {out_p2}")
    
    # Parse local crop coordinates
    local_x, local_y = None, None
    match_xy = re.search(r"x\s*[:=]\s*([0-9.]+).*?y\s*[:=]\s*([0-9.]+)", out_p2, re.IGNORECASE)
    if match_xy:
        local_x, local_y = float(match_xy.group(1)), float(match_xy.group(2))
    else:
        coords_m2 = re.search(r"\[?\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]?", out_p2)
        if coords_m2:
            d1, d2, d3, d4 = [float(x) for x in coords_m2.groups()]
            if all(c <= 1.0 for c in (d1, d2, d3, d4)):
                d1, d2, d3, d4 = d1 * crop_h, d2 * crop_w, d3 * crop_h, d4 * crop_w
            elif all(c <= 1000.0 for c in (d1, d2, d3, d4)) and any(c < 1000 for c in (d1, d2, d3, d4)):
                d1, d2, d3, d4 = (d1/1000.0)*crop_h, (d2/1000.0)*crop_w, (d3/1000.0)*crop_h, (d4/1000.0)*crop_w
            local_x = (min(d2, d4) + max(d2, d4)) / 2.0
            local_y = (min(d1, d3) + max(d1, d3)) / 2.0
        else:
            match_pair = re.search(r"[\(\[\s]*([0-9]+)\s*[,x\s]\s*([0-9]+)[\)\]\s]*", out_p2)
            if match_pair:
                local_x, local_y = float(match_pair.group(1)), float(match_pair.group(2))
                
    if local_x is None or local_y is None:
        print("❌ Could not resolve local crop coordinates. Falling back to single-pass...")
        return verify_vision_target(instruction, output_path)
        
    global_x = max(0, min(int(round(crop_left + local_x)), orig_width - 1))
    global_y = max(0, min(int(round(crop_top + local_y)), orig_height - 1))
    print(f"🎯 2-Pass Resolved Global Target: X={global_x}, Y={global_y}")
    
    draw = ImageDraw.Draw(screenshot)
    r1, r2, r3, dot_r = 70, 66, 36, 16
    draw.ellipse([(global_x - r1, global_y - r1), (global_x + r1, global_y + r1)], outline="#FFFFFF", width=8)
    draw.ellipse([(global_x - r2, global_y - r2), (global_x + r2, global_y + r2)], outline="#FF007F", width=8)
    draw.ellipse([(global_x - r3, global_y - r3), (global_x + r3, global_y + r3)], outline="#FF007F", width=6)
    draw.ellipse([(global_x - dot_r, global_y - dot_r), (global_x + dot_r, global_y + dot_r)], fill="#FF007F", outline="#FFFFFF", width=3)
    
    ch_in, ch_out = 22, 110
    draw.line([(global_x - ch_out, global_y), (global_x - ch_in, global_y)], fill="#FF007F", width=6)
    draw.line([(global_x + ch_in, global_y), (global_x + ch_out, global_y)], fill="#FF007F", width=6)
    draw.line([(global_x, global_y - ch_out), (global_x, global_y - ch_in)], fill="#FF007F", width=6)
    draw.line([(global_x, global_y + ch_in), (global_x, global_y + ch_out)], fill="#FF007F", width=6)

    screenshot.save(output_path)
    print(f"💾 Saved 2-Pass verified screenshot to: {os.path.abspath(output_path)}")
    try:
        os.startfile(os.path.abspath(output_path))
    except Exception:
        pass
    return True, (global_x, global_y)

if __name__ == "__main__":
    print("--- Stage 1: Visual Verification Sandbox ---")
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        if args[0] in ("--two-pass", "-2p"):
            query = " ".join(args[1:])
            hierarchical_locate_and_verify(query)
        else:
            query = " ".join(args)
            verify_vision_target(query)
    else:
        while True:
            target = input("\nEnter UI target to locate & verify (prefix with '-2p ' for 2-pass crop, or 'q' to quit): ").strip()
            if target.lower() in ('q', 'quit', 'exit'):
                break
            if target.startswith("-2p "):
                hierarchical_locate_and_verify(target[4:].strip())
            elif target:
                verify_vision_target(target)
