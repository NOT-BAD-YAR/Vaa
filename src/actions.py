import os
import sys
import socket
import webbrowser
import subprocess
import requests
import pyautogui
from PIL import Image
import base64
from src.vision import take_screenshot, capture_camera_image, start_screen_recording, stop_screen_recording, locate_and_verify_ui, locate_and_click_ui
from src.config import DEFAULT_MODEL, query_ollama, get_gemini_client, GEMINI_VISION_MODEL, generate_with_retry
from src.logger import log

def search_windows_app_paths(query: str) -> list[str]:
    """
    Fast Windows Searcher (~10ms): Searches Start Menu & Desktop shortcuts
    for applications matching keywords in query.
    """
    query_clean = query.lower().replace("start ", "").replace(".exe", "").replace(".lnk", "").replace('"', '').replace("'", "").strip()
    keywords = [kw for kw in query_clean.split() if len(kw) > 1]
    if not keywords:
        return []
        
    search_dirs = [
        "C:\\ProgramData\\Microsoft\\Windows\\Start Menu",
        os.path.expanduser("~\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu"),
        os.path.expanduser("~\\Desktop"),
        "C:\\Users\\Public\\Desktop"
    ]
    
    matches = []
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for r, _, fs in os.walk(d):
            for f in fs:
                if f.endswith(('.lnk', '.exe')):
                    f_lower = f.lower()
                    if all(kw in f_lower for kw in keywords) or any(kw in f_lower for kw in keywords if len(kw) >= 4):
                        full_path = os.path.join(r, f)
                        if full_path not in matches:
                            matches.append(full_path)
    return matches[:10]

def execute_action(action_str: str, user_statement: str = "") -> str:
    """
    Executes universal structured command templates or legacy action names.
    Format examples:
      RUN_COMMAND: calc.exe
      OPEN_URL: https://www.google.com
      SYSTEM: SLEEP
      NETWORK: IP_LOOKUP
      VISION: CAMERA_ANALYZE
    """
    action_str = action_str.strip()
    log.info(f"[Action Executor] Executing action: {action_str}")
    
    # Handle universal RUN_COMMAND template
    if action_str.startswith("RUN_COMMAND:"):
        cmd = action_str.split("RUN_COMMAND:", 1)[1].strip()
        clean_cmd = cmd.strip('"\'')
        
        # 1. If exact file path exists (like a resolved .lnk or .exe), start file natively
        if os.path.exists(clean_cmd):
            try:
                os.startfile(clean_cmd)
                return f"Opened application: {os.path.basename(clean_cmd)}"
            except Exception as e:
                raise RuntimeError(f"Failed to launch file '{clean_cmd}': {str(e)}")
                
        # 2. If it starts with 'start ', run via subprocess.run
        if cmd.lower().startswith("start "):
            res = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Command execution failed: {res.stderr.strip() or res.stdout.strip()}")
            return f"Executed command: {cmd}"
            
        # 3. Try executing with subprocess.run to verify recognition
        res = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            raise RuntimeError(f"Command execution failed: {err_msg}")
        return f"Executed command: {cmd}"

    # Handle universal OPEN_URL template
    elif action_str.startswith("OPEN_URL:"):
        url = action_str.split("OPEN_URL:", 1)[1].strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return f"Opening web browser to {url}"
        except Exception as e:
            raise RuntimeError(f"Failed to open URL '{url}': {str(e)}")

    # Handle universal SYSTEM commands
    elif action_str.startswith("SYSTEM:"):
        sys_cmd = action_str.split("SYSTEM:", 1)[1].strip().upper()
        if sys_cmd == "SLEEP":
            return "Going to sleep mode. Say awake when you need me."
        elif sys_cmd == "EXIT":
            return "EXIT_APP"
        elif sys_cmd == "SCREENSHOT":
            try:
                filepath = take_screenshot()
                return f"Screenshot captured and saved to {filepath}."
            except Exception as e:
                raise RuntimeError(f"Screenshot failed: {str(e)}")
        elif sys_cmd == "START_RECORDING":
            return start_screen_recording()
        elif sys_cmd == "STOP_RECORDING":
            return stop_screen_recording()
        elif sys_cmd == "MINIMIZE":
            pyautogui.hotkey("win", "down")
            return "Minimized active application."
        else:
            raise ValueError(f"Unknown system command: {sys_cmd}")

    # Handle universal NETWORK commands
    elif action_str.startswith("NETWORK:"):
        net_cmd = action_str.split("NETWORK:", 1)[1].strip().upper()
        if net_cmd == "IP_LOOKUP":
            try:
                res = requests.get("https://api.ipify.org?format=json", timeout=5).json()
                ip = res.get("ip")
                return f"Your public IP address is {ip}."
            except Exception:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                return f"Your local IP address is {local_ip}."
        elif net_cmd == "WEATHER":
            try:
                res = requests.get("https://wttr.in/?format=3", timeout=5).text.strip()
                return f"The weather right now is: {res}"
            except Exception:
                webbrowser.open("https://www.weather.com")
                return "Opening weather forecast in browser."
        else:
            raise ValueError(f"Unknown network command: {net_cmd}")

    # Handle universal VISION commands
    elif action_str.startswith("VISION:"):
        vis_cmd = action_str.split("VISION:", 1)[1].strip()
        vis_cmd_upper = vis_cmd.upper()
        if vis_cmd_upper == "CAMERA_ANALYZE":
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
                response_text = response.text if response.text else ""
                return f"Looking at the webcam: {response_text.strip()}"
            except Exception as e:
                raise RuntimeError(f"Could not analyze webcam image: {str(e)}")
        elif vis_cmd_upper.startswith("LOCATE_VERIFY:") or vis_cmd_upper.startswith("VERIFY:"):
            target = vis_cmd.split(":", 1)[1].strip()
            log.info(f"[Action Execution] Running locate_and_verify_ui on target: {target}")
            return locate_and_verify_ui(target)
        elif vis_cmd_upper.startswith("LOCATE_CLICK:") or vis_cmd_upper.startswith("CLICK:"):
            target = vis_cmd.split(":", 1)[1].strip()
            log.info(f"[Action Execution] Running locate_and_click_ui on target: {target}")
            return locate_and_click_ui(target)
        else:
            raise ValueError(f"Unknown vision command: {vis_cmd}")

    # Handle universal KEYBOARD commands
    elif action_str.startswith("KEYBOARD:"):
        kb_cmd = action_str.split("KEYBOARD:", 1)[1].strip()
        kb_upper = kb_cmd.upper()
        if kb_upper.startswith("TYPE:"):
            text_to_type = kb_cmd.split(":", 1)[1].strip()
            log.info(f"[Action Execution] Typing keyboard text: {text_to_type[:40]}...")
            pyautogui.write(text_to_type, interval=0.02)
            return f"Typed text: {text_to_type[:30]}..."
        elif kb_upper.startswith("HOTKEY:"):
            keys = [k.strip().lower() for k in kb_cmd.split(":", 1)[1].split(",")]
            log.info(f"[Action Execution] Executing hotkey: {keys}")
            pyautogui.hotkey(*keys)
            return f"Pressed hotkeys: {' + '.join(keys)}"
        elif kb_upper.startswith("PRESS:"):
            key = kb_cmd.split(":", 1)[1].strip().lower()
            log.info(f"[Action Execution] Pressing key: {key}")
            pyautogui.press(key)
            return f"Pressed key: {key}"
        else:
            raise ValueError(f"Unknown keyboard command: {kb_cmd}")

    # Legacy fallback handlers for backward compatibility
    elif action_str == "ACTION_AWAKEN":
        return "I am awake and ready to assist you."
    elif action_str == "ACTION_SLEEP":
        return "Going to sleep mode. Say awake when you need me."
    elif action_str == "ACTION_APPEAR":
        return "I am here on your screen."
    elif action_str == "ACTION_EXIT":
        return "EXIT_APP"
    elif action_str == "ACTION_OPEN_NOTEPAD":
        subprocess.Popen(["notepad.exe"])
        return "Opening Notepad."
    elif action_str == "ACTION_OPEN_WORD":
        os.system("start winword")
        return "Opening Microsoft Word."
    elif action_str == "ACTION_OPEN_EXCEL":
        os.system("start excel")
        return "Opening Microsoft Excel."
    elif action_str == "ACTION_OPEN_POWERPOINT":
        os.system("start powerpnt")
        return "Opening Microsoft PowerPoint."
    elif action_str == "ACTION_OPEN_COMMAND_PROMPT":
        os.system("start cmd")
        return "Opening Command Prompt."
    elif action_str == "ACTION_OPEN_CAMERA":
        os.system("start microsoft.windows.camera:")
        return "Opening Windows Camera app."
    elif action_str == "ACTION_OPEN_CALCULATOR":
        subprocess.Popen(["calc.exe"])
        return "Opening Calculator."
    elif action_str == "ACTION_FIND_MY_IP":
        return execute_action("NETWORK: IP_LOOKUP", user_statement)
    elif action_str == "ACTION_OPEN_YOUTUBE":
        return execute_action("OPEN_URL: https://www.youtube.com", user_statement)
    elif action_str == "ACTION_CHECK_WEATHER":
        return execute_action("NETWORK: WEATHER", user_statement)
    elif action_str == "ACTION_TAKE_SCREENSHOT":
        return execute_action("SYSTEM: SCREENSHOT", user_statement)
    elif action_str == "ACTION_START_SCREEN_RECORDING":
        return execute_action("SYSTEM: START_RECORDING", user_statement)
    elif action_str == "ACTION_STOP_SCREEN_RECORDING":
        return execute_action("SYSTEM: STOP_RECORDING", user_statement)
    elif action_str == "ACTION_MINIMIZE_DISAPPEAR_APPLICATION":
        return execute_action("SYSTEM: MINIMIZE", user_statement)
    elif action_str == "ACTION_OPEN_BROWSER_WEBSITE":
        return execute_action("OPEN_URL: https://www.google.com", user_statement)
    elif action_str == "ACTION_WHAT_DO_YOU_SEE_IN_CAMERA":
        return execute_action("VISION: CAMERA_ANALYZE", user_statement)
    else:
        # If passed raw OS command as fallback
        try:
            subprocess.Popen(action_str, shell=True)
            return f"Executed: {action_str}"
        except Exception as e:
            raise RuntimeError(f"Unknown action or failed command: {action_str}")
