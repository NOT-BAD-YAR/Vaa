import time
import threading
from datetime import datetime
import cv2
import pyautogui
import numpy as np
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
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
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
