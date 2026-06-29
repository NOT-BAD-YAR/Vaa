import re
import time
from src.config import DEFAULT_MODEL, query_ollama, get_gemini_client, GEMINI_VISION_MODEL, generate_with_retry
from src.actions import execute_action, search_windows_app_paths

UNIVERSAL_SYSTEM_PROMPT = """You are Vaa, an intelligent virtual personal assistant on Windows.
Analyze the user's input.
If the user is having a casual conversation, asking general questions, or chatting, respond naturally as a friendly AI assistant.
If the user wants to perform an action on the computer, control applications, open websites, or inspect system/network state, you MUST output ONLY a structured command template tag in the exact format:
<CMD>COMMAND_TYPE: target_or_details</CMD>

Available COMMAND_TYPEs:
1. RUN_COMMAND: For launching OS applications, Windows commands, or executables.
   Examples: <CMD>RUN_COMMAND: notepad.exe</CMD>, <CMD>RUN_COMMAND: calc.exe</CMD>, <CMD>RUN_COMMAND: start winword</CMD>, <CMD>RUN_COMMAND: start excel</CMD>, <CMD>RUN_COMMAND: start cmd</CMD>, <CMD>RUN_COMMAND: start microsoft.windows.camera:</CMD>
2. OPEN_URL: For opening websites in the browser.
   Examples: <CMD>OPEN_URL: https://www.google.com</CMD>, <CMD>OPEN_URL: https://www.youtube.com</CMD>
3. SYSTEM: For system-level controls.
   Examples: <CMD>SYSTEM: SLEEP</CMD>, <CMD>SYSTEM: EXIT</CMD>, <CMD>SYSTEM: SCREENSHOT</CMD>, <CMD>SYSTEM: START_RECORDING</CMD>, <CMD>SYSTEM: STOP_RECORDING</CMD>, <CMD>SYSTEM: MINIMIZE</CMD>
4. NETWORK: For network information.
   Examples: <CMD>NETWORK: IP_LOOKUP</CMD>, <CMD>NETWORK: WEATHER</CMD>
5. VISION: For webcam visual analysis.
   Example: <CMD>VISION: CAMERA_ANALYZE</CMD>

IMPORTANT: When generating an action tag `<CMD>...</CMD>`, do NOT include any extra conversational text before or after the tag. Output ONLY the `<CMD>...</CMD>` tag."""

def classify_requires_online(statement: str) -> bool:
    """
    Intent Router: Determines if the request requires online network / vision APIs vs local execution.
    """
    stmt_lower = statement.lower()
    online_keywords = [
        "what do you see", "camera", "webcam", "look at", "vision",
        "ip address", "public ip", "weather", "forecast", "search online",
        "google", "youtube", "website", "browse", "news"
    ]
    return any(kw in stmt_lower for kw in online_keywords)

def generate_model_response(prompt: str, use_online: bool) -> str:
    """
    Routes query to Online Gemini API or Local Ollama based on routing classification.
    Has fallback capability if Local Ollama is offline.
    """
    if use_online:
        try:
            client = get_gemini_client()
            response = generate_with_retry(client, contents=[prompt], model=GEMINI_VISION_MODEL)
            return response.text.strip()
        except Exception as e:
            print(f"[Router Warning]: Online API failed ({e}). Falling back to Local Ollama...")
            return query_ollama(prompt=prompt, model=DEFAULT_MODEL)
    else:
        try:
            return query_ollama(prompt=prompt, model=DEFAULT_MODEL)
        except Exception as e:
            print(f"[Router Warning]: Local Ollama failed ({e}). Falling back to Online API...")
            client = get_gemini_client()
            response = generate_with_retry(client, contents=[prompt], model=GEMINI_VISION_MODEL)
            return response.text.strip()

def extract_command_tag(text: str) -> str | None:
    """Extracts content inside <CMD>...</CMD> tags."""
    match = re.search(r'<CMD>(.*?)</CMD>', text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def resolve_windows_command(cmd_str: str, statement: str, use_online: bool) -> str:
    """
    Fast resolution for Windows applications: searches Start Menu & Desktop shortcuts
    and sends matches to LLM to construct exact executable command.
    """
    if not cmd_str.startswith("RUN_COMMAND:"):
        return cmd_str
    cmd_target = cmd_str.split("RUN_COMMAND:", 1)[1].strip().strip('"\'')
    import os, shutil
    if os.path.exists(cmd_target) or shutil.which(cmd_target.split()[0]) or cmd_target.lower().startswith("start ") or cmd_target.lower() in ["calc.exe", "notepad.exe", "cmd.exe", "explorer.exe"]:
        return cmd_str
        
    print(f"[Fast Windows Finder]: Searching for '{cmd_target}' across Windows shortcuts...")
    matches = search_windows_app_paths(cmd_target)
    if not matches:
        return cmd_str
        
    prompt = (
        f"User requested application: '{statement}' (target: '{cmd_target}').\n"
        f"We fast-searched the Windows system and found these exact matching application files/shortcuts:\n"
        + "\n".join([f"{i+1}. {m}" for i, m in enumerate(matches)]) + "\n\n"
        "Output ONLY the exact command template to run the correct file using RUN_COMMAND. "
        "Always enclose file paths containing spaces or .lnk extensions in double quotes. "
        "Example format: <CMD>RUN_COMMAND: \"C:\\path\\to\\file.lnk\"</CMD>."
    )
    resolved_output = generate_model_response(prompt, use_online=use_online)
    new_tag = extract_command_tag(resolved_output)
    if new_tag:
        print(f"[Resolved Windows Path]: {new_tag}")
        return new_tag
    return cmd_str

def process_statement(statement: str, is_sleeping: bool = False) -> tuple[str, bool, str | None]:
    """
    Processes user statement through Intent Router, Universal Command Template,
    and Self-Correction Retry Loop.
    Returns (response_text, is_action_executed, new_state).
    """
    if not statement or not statement.strip():
        return "", False, None
        
    # Check simple wake keywords if sleeping
    if is_sleeping:
        if any(w in statement.lower() for w in ["awake", "wake up", "come back"]):
            res = execute_action("ACTION_AWAKEN", statement)
            return res, True, "AWAKE"
        return "", False, "SLEEPING"
        
    # Step 1: Intent Router Analysis
    requires_online = classify_requires_online(statement)
    print(f"[Intent Router]: Request routed to {'Online Gemini API' if requires_online else 'Local Ollama Model'}")
    
    full_prompt = f"{UNIVERSAL_SYSTEM_PROMPT}\n\nUser statement: {statement}"
    
    # Step 2: Generate Model Output
    llm_output = generate_model_response(full_prompt, use_online=requires_online)
    
    # Step 3: Parse Command Tag & Execute with Self-Correction Loop
    cmd_str = extract_command_tag(llm_output)
    
    # Legacy fallback: check if raw ACTION_* tag returned without <CMD>
    if not cmd_str:
        for legacy_act in ["ACTION_AWAKEN", "ACTION_SLEEP", "ACTION_APPEAR", "ACTION_EXIT"]:
            if legacy_act in llm_output:
                cmd_str = legacy_act
                break

    if not cmd_str:
        # Normal conversation response
        return llm_output, False, None
        
    print(f"[Identified Command Template]: {cmd_str}")
    
    # Attempt execution with Self-Correction Retry Loop
    max_retries = 2
    current_cmd = cmd_str
    
    for attempt in range(max_retries + 1):
        try:
            current_cmd = resolve_windows_command(current_cmd, statement, requires_online)
            result = execute_action(current_cmd, statement)
            
            # State transitions
            new_state = None
            if current_cmd in ["SYSTEM: SLEEP", "ACTION_SLEEP"]:
                new_state = "SLEEPING"
            elif current_cmd in ["SYSTEM: EXIT", "ACTION_EXIT"]:
                return "EXIT_APP", True, None
                
            return result, True, new_state
            
        except Exception as e:
            err_msg = str(e)
            print(f"[Execution Error on attempt {attempt+1}]: {err_msg}")
            
            if attempt == max_retries:
                return f"I tried executing that action, but encountered an error: {err_msg}", False, None
                
            print("[Triggering Self-Correction Retry Loop...]")
            retry_prompt = (
                f"{UNIVERSAL_SYSTEM_PROMPT}\n\n"
                f"Previous command attempt `<CMD>{current_cmd}</CMD>` failed with error:\n{err_msg}\n\n"
                f"User Request: {statement}\n"
                f"Correct your mistake and output ONLY the valid executable `<CMD>...</CMD>` tag."
            )
            retry_output = generate_model_response(retry_prompt, use_online=requires_online)
            new_cmd = extract_command_tag(retry_output)
            if new_cmd:
                current_cmd = new_cmd
                print(f"[Self-Corrected Command]: {current_cmd}")
            else:
                return f"Action failed after retry: {err_msg}", False, None
