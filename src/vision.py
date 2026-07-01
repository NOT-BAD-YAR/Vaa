import time
import threading
from datetime import datetime
# pyrefly: ignore [missing-import]
import cv2
import pyautogui
import numpy as np
# pyrefly: ignore [missing-import]
from PIL import Image
from src.config import SCREENSHOTS_DIR, CAMERA_DIR, RECORDINGS_DIR

# Global variables for screen recording state
_recording_thread = None
_stop_recording_flag = False
_current_recording_path = None

def take_screenshot() -> str:
    """Captures the entire screen and saves it as a PNG image."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SCREENSHOTS_DIR / f"screenshot_{timestamp}.png"
    screenshot = pyautogui.screenshot()
    screenshot.save(filepath)
    return str(filepath)

def capture_camera_image() -> str:
    """Captures a single frame from the default webcam and saves it as a JPG image."""
    # Try DirectShow backend first on Windows, fallback to default backend
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]
    frame = None
    
    for backend in backends:
        cap = cv2.VideoCapture(0, backend)
        if not cap.isOpened():
            continue
            
        # Warm up camera and try reading multiple frames
        for _ in range(10):
            time.sleep(0.1)
            ret, temp_frame = cap.read()
            if ret and temp_frame is not None:
                frame = temp_frame
                break
                
        cap.release()
        if frame is not None:
            break
            
    if frame is None:
        raise RuntimeError("Failed to read frame from webcam. Ensure no other application (like Zoom or Teams) is using the camera.")
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = CAMERA_DIR / f"camera_{timestamp}.jpg"
    
    cv2.imwrite(str(filepath), frame)
    return str(filepath)

def _record_screen_worker(filepath: str, fps: int = 10):
    global _stop_recording_flag
    screen_width, screen_height = pyautogui.size()
    fourcc = cv2.VideoWriter_fourcc(*"mp4v") # pyright: ignore[reportAttributeAccessIssue]
    out = cv2.VideoWriter(filepath, fourcc, fps, (screen_width, screen_height))
    
    frame_duration = 1.0 / fps
    while not _stop_recording_flag:
        start_time = time.time()
        img = pyautogui.screenshot()
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        out.write(frame)
        
        elapsed = time.time() - start_time
        sleep_time = max(0, frame_duration - elapsed)
        time.sleep(sleep_time)
        
    out.release()

def start_screen_recording() -> str:
    """Starts screen recording in a background thread."""
    global _recording_thread, _stop_recording_flag, _current_recording_path
    if _recording_thread is not None and _recording_thread.is_alive():
        return "Screen recording is already in progress."
        
    _stop_recording_flag = False
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = str(RECORDINGS_DIR / f"recording_{timestamp}.mp4")
    _current_recording_path = filepath
    
    _recording_thread = threading.Thread(target=_record_screen_worker, args=(filepath,), daemon=True)
    _recording_thread.start()
    return f"Started screen recording saving to {filepath}"

def stop_screen_recording() -> str:
    """Stops the active screen recording."""
    global _recording_thread, _stop_recording_flag, _current_recording_path
    if _recording_thread is None or not _recording_thread.is_alive():
        return "No active screen recording found."
        
    _stop_recording_flag = True
    _recording_thread.join(timeout=3.0)
    _recording_thread = None
    saved_path = _current_recording_path
    _current_recording_path = None
    return f"Stopped screen recording. Saved at {saved_path}"

from src.config import get_gemini_client, GEMINI_VISION_MODEL, generate_with_retry
from src.logger import log
import re

def get_screen_resolution() -> tuple[int, int]:
    """Returns dynamic monitor resolution (width, height)."""
    width, height = pyautogui.size()
    return int(width), int(height)

def _extract_coords_and_action(output_text: str, orig_width: int, orig_height: int) -> tuple[int | None, int | None, str]:
    """
    Extracts exact (x, y) coordinates and mouse action from Gemini API output using regex.
    Supports structured formats e.g.:
      x: 350, y: 400, action: CLICK
      [x: 1890, y: 15] action: DOUBLE_CLICK
      [ymin, xmin, ymax, xmax]
    """
    center_x, center_y = None, None
    action = "CLICK"

    # Identify action type if present
    output_upper = output_text.upper()
    for act in ["DOUBLE_CLICK", "RIGHT_CLICK", "DRAG", "HOVER", "CLICK"]:
        if act in output_upper:
            action = act
            break

    # Format 1: Explicit x and y labels, e.g. "x: 1050, y: 20"
    match_xy = re.search(r"x\s*[:=]\s*([0-9.]+).*?y\s*[:=]\s*([0-9.]+)", output_text, re.IGNORECASE)
    if not match_xy:
        match_yx = re.search(r"y\s*[:=]\s*([0-9.]+).*?x\s*[:=]\s*([0-9.]+)", output_text, re.IGNORECASE)
        if match_yx:
            center_y, center_x = float(match_yx.group(1)), float(match_yx.group(2))
    else:
        center_x, center_y = float(match_xy.group(1)), float(match_xy.group(2))

    # Format 2: 4-value bounding box [ymin, xmin, ymax, xmax]
    if center_x is None or center_y is None:
        coords_match = re.search(r"\[?\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]?", output_text)
        if coords_match:
            c1, c2, c3, c4 = [float(x) for x in coords_match.groups()]
            if all(c <= 1.0 for c in (c1, c2, c3, c4)):
                c1, c2, c3, c4 = c1 * orig_height, c2 * orig_width, c3 * orig_height, c4 * orig_width
            elif all(c <= 1000.0 for c in (c1, c2, c3, c4)) and any(c < 1000 for c in (c1, c2, c3, c4)):
                c1, c2, c3, c4 = (c1/1000.0)*orig_height, (c2/1000.0)*orig_width, (c3/1000.0)*orig_height, (c4/1000.0)*orig_width
                
            ymin, xmin, ymax, xmax = min(c1, c3), min(c2, c4), max(c1, c3), max(c2, c4)
            center_x = (xmin + xmax) / 2.0
            center_y = (ymin + ymax) / 2.0

    # Format 3: Simple 2-value coordinate pair (x, y)
    if center_x is None or center_y is None:
        match_pair = re.search(r"[\(\[\s]*([0-9]+)\s*[,x\s]\s*([0-9]+)[\)\]\s]*", output_text)
        if match_pair:
            center_x, center_y = float(match_pair.group(1)), float(match_pair.group(2))

    if center_x is not None and center_y is not None:
        cx = max(0, min(int(round(center_x)), orig_width - 1))
        cy = max(0, min(int(round(center_y)), orig_height - 1))
        return cx, cy, action
    return None, None, action

def query_gemini_vision_for_coords(instruction: str, custom_prompt: str | None = None) -> tuple[int | None, int | None, str, str]:
    """
    Takes a desktop screenshot and sends it to Online Gemini API with the target instruction and active resolution.
    Returns (cx, cy, action, raw_model_output).
    """
    width, height = get_screen_resolution()
    log.info(f"[Vision Engine] Capturing screenshot at dynamic resolution {width}x{height}...")
    screenshot_path = take_screenshot()
    img = Image.open(screenshot_path)

    if custom_prompt:
        prompt = custom_prompt
    else:
        prompt = (
            f"You are analyzing a Windows desktop screenshot with resolution {width}x{height}.\n"
            f"Target interface element to locate: '{instruction}'.\n"
            f"Find the exact center point pixel coordinates (x, y) of this element.\n"
            f"Return ONLY in exact structured format: `x: <number>, y: <number>, action: CLICK`.\n"
            f"If it requires double click or right click, use action: DOUBLE_CLICK or RIGHT_CLICK. Be concise and accurate."
        )

    log.debug(f"[Vision Engine] Sending prompt to Online Gemini ({GEMINI_VISION_MODEL}):\n{prompt}")
    try:
        client = get_gemini_client()
        response = generate_with_retry(client, contents=[img, prompt], model=GEMINI_VISION_MODEL)
        output_text = response.text.strip() if response.text else ""
        log.info(f"[Vision Engine Output]: {output_text}")
    except Exception as e:
        log.error(f"[Vision Engine Error]: Online Gemini API call failed: {e}")
        return None, None, "CLICK", f"API Error: {str(e)}"

    cx, cy, action = _extract_coords_and_action(output_text, width, height)
    if cx is not None and cy is not None:
        log.info(f"[Regex Extractor] Successfully parsed coordinates X={cx}, Y={cy}, Action={action}")
    else:
        log.warning(f"[Regex Extractor] Failed to parse valid coordinates from output: {output_text}")
        
    return cx, cy, action, output_text

def locate_and_verify_ui(instruction: str) -> str:
    """Takes screenshot, queries Online Gemini for UI target coordinates, and paints a verification marker."""
    from PIL import ImageDraw
    
    cx, cy, action, raw_output = query_gemini_vision_for_coords(instruction)
    if cx is None or cy is None:
        return f"Could not locate '{instruction}' on screen. Model output: {raw_output}"
        
    screenshot = pyautogui.screenshot()
    draw = ImageDraw.Draw(screenshot)
    
    r1 = 70
    draw.ellipse([(cx - r1, cy - r1), (cx + r1, cy + r1)], outline="#FFFFFF", width=8)
    r2 = 66
    draw.ellipse([(cx - r2, cy - r2), (cx + r2, cy + r2)], outline="#FF007F", width=8)
    r3 = 36
    draw.ellipse([(cx - r3, cy - r3), (cx + r3, cy + r3)], outline="#FF007F", width=6)
    dot_r = 16
    draw.ellipse([(cx - dot_r, cy - dot_r), (cx + dot_r, cy + dot_r)], fill="#FF007F", outline="#FFFFFF", width=3)
    
    ch_in = 22
    ch_out = 110
    draw.line([(cx - ch_out, cy), (cx - ch_in, cy)], fill="#FF007F", width=6)
    draw.line([(cx + ch_in, cy), (cx + ch_out, cy)], fill="#FF007F", width=6)
    draw.line([(cx, cy - ch_out), (cx, cy - ch_in)], fill="#FF007F", width=6)
    draw.line([(cx, cy + ch_in), (cx, cy + ch_out)], fill="#FF007F", width=6)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SCREENSHOTS_DIR / f"verified_{timestamp}.png"
    screenshot.save(filepath)
    log.info(f"[Vision Verify] Verification bullseye saved to {filepath}")
        
    return f"Located '{instruction}' at X={cx}, Y={cy}. Verified pink marker saved to {filepath}"

def locate_and_click_ui(instruction: str) -> str:
    """Takes screenshot, locates UI element via Online Gemini API, and performs mouse action."""
    cx, cy, action, raw_output = query_gemini_vision_for_coords(instruction)
    if cx is None or cy is None:
        return f"Could not locate '{instruction}' on screen. Model output: {raw_output}"
        
    log.info(f"[Mouse Execution] Moving cursor to ({cx}, {cy}) and executing {action}...")
    pyautogui.moveTo(cx, cy, duration=0.4)
    
    if action == "DOUBLE_CLICK":
        pyautogui.doubleClick()
    elif action == "RIGHT_CLICK":
        pyautogui.rightClick()
    else:
        pyautogui.click()
        
    return f"Located and executed {action} on '{instruction}' at X={cx}, Y={cy}."

