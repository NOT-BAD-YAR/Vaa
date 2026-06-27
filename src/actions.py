import os
import sys
import socket
import webbrowser
import subprocess
import requests
import pyautogui
from PIL import Image
import base64
from src.vision import take_screenshot, capture_camera_image, start_screen_recording, stop_screen_recording
from src.config import DEFAULT_MODEL, query_ollama, get_gemini_client, GEMINI_VISION_MODEL, generate_with_retry

def execute_action(action_name: str, user_statement: str = "") -> str:
    """Executes the corresponding action based on the ACTION_* name returned by the LLM."""
    action_name = action_name.strip()
    
    if action_name == "ACTION_AWAKEN":
        return "I am awake and ready to assist you."
    elif action_name == "ACTION_SLEEP":
        return "Going to sleep mode. Say awake when you need me."
    elif action_name == "ACTION_APPEAR":
        return "I am here on your screen."
    elif action_name == "ACTION_EXIT":
        return "EXIT_APP"
    elif action_name == "ACTION_OPEN_NOTEPAD":
        subprocess.Popen(["notepad.exe"])
        return "Opening Notepad."
    elif action_name == "ACTION_OPEN_WORD":
        os.system("start winword")
        return "Opening Microsoft Word."
    elif action_name == "ACTION_OPEN_EXCEL":
        os.system("start excel")
        return "Opening Microsoft Excel."
    elif action_name == "ACTION_OPEN_POWERPOINT":
        os.system("start powerpnt")
        return "Opening Microsoft PowerPoint."
    elif action_name == "ACTION_OPEN_COMMAND_PROMPT":
        os.system("start cmd")
        return "Opening Command Prompt."
    elif action_name == "ACTION_OPEN_CAMERA":
        os.system("start microsoft.windows.camera:")
        return "Opening Windows Camera app."
    elif action_name == "ACTION_OPEN_CALCULATOR":
        subprocess.Popen(["calc.exe"])
        return "Opening Calculator."
    elif action_name == "ACTION_FIND_MY_IP":
        try:
            res = requests.get("https://api.ipify.org?format=json", timeout=5).json()
            ip = res.get("ip")
            return f"Your public IP address is {ip}."
        except Exception:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return f"Your local IP address is {local_ip}."
    elif action_name == "ACTION_OPEN_YOUTUBE":
        webbrowser.open("https://www.youtube.com")
        return "Opening YouTube in your browser."
    elif action_name == "ACTION_CHECK_WEATHER":
        try:
            res = requests.get("https://wttr.in/?format=3", timeout=5).text.strip()
            return f"The weather right now is: {res}"
        except Exception:
            webbrowser.open("https://www.weather.com")
            return "Opening weather forecast in browser."
    elif action_name == "ACTION_TAKE_SCREENSHOT":
        try:
            filepath = take_screenshot()
            return f"Screenshot captured and saved to {filepath}."
        except Exception as e:
            return f"Failed to take screenshot: {str(e)}"
    elif action_name == "ACTION_START_SCREEN_RECORDING":
        return start_screen_recording()
    elif action_name == "ACTION_STOP_SCREEN_RECORDING":
        return stop_screen_recording()
    elif action_name == "ACTION_MINIMIZE_DISAPPEAR_APPLICATION":
        pyautogui.hotkey("win", "down")
        return "Minimized active application."
    elif action_name == "ACTION_OPEN_BROWSER_WEBSITE":
        webbrowser.open("https://www.google.com")
        return "Opening your web browser."
    elif action_name == "ACTION_WHAT_DO_YOU_SEE_IN_CAMERA":
        try:
            img_path = capture_camera_image()
            client = get_gemini_client()
            img = Image.open(img_path)
            prompt = "What do you see in this camera capture? Describe concisely."
            response = generate_with_retry(
                client,
                contents=[img, prompt],
                model=GEMINI_VISION_MODEL
            )
            return f"Looking at the webcam: {response.text.strip()}"
        except Exception as e:
            return f"Could not analyze webcam image: {str(e)}"
    else:
        return f"Action {action_name} executed."
