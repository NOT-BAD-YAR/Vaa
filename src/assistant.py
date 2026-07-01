import re
import time
from src.config import DEFAULT_MODEL, query_ollama, get_gemini_client, GEMINI_VISION_MODEL, generate_with_retry
from src.actions import execute_action, search_windows_app_paths
from src.logger import log

UNIVERSAL_SYSTEM_PROMPT = """You are Vaa, an intelligent virtual personal assistant on Windows.
Analyze the user's input and current step history.
If the user is having a casual conversation, asking general knowledge questions, or chatting without needing OS/desktop actions, respond naturally as a friendly AI assistant.

If the user wants to perform tasks on the computer (single step or multi-step), you act as a Dynamic Step Orchestrator. Output ONLY a single structured command template tag for the NEXT step to execute:
<CMD>COMMAND_TYPE: target_or_details</CMD>

Available COMMAND_TYPEs:
1. RUN_COMMAND: For launching OS applications, Windows settings, or executables.
   Examples: <CMD>RUN_COMMAND: notepad.exe</CMD>, <CMD>RUN_COMMAND: calc.exe</CMD>, <CMD>RUN_COMMAND: start ms-settings:display</CMD>
2. VISION: For desktop screen GUI localization and clicking/verifying elements.
   Examples: <CMD>VISION: LOCATE_CLICK: Notepad text editing area</CMD>, <CMD>VISION: LOCATE_CLICK: Display resolution dropdown button</CMD>
3. KEYBOARD: For typing text or pressing hotkeys.
   Examples: <CMD>KEYBOARD: TYPE: Dear Manager, I am writing to request leave...</CMD>, <CMD>KEYBOARD: HOTKEY: ctrl,s</CMD>, <CMD>KEYBOARD: PRESS: enter</CMD>
4. OPEN_URL: For opening websites in the browser.
   Examples: <CMD>OPEN_URL: https://www.google.com</CMD>
5. SYSTEM: For system-level controls.
   Examples: <CMD>SYSTEM: SLEEP</CMD>, <CMD>SYSTEM: EXIT</CMD>, <CMD>SYSTEM: SCREENSHOT</CMD>
6. NETWORK: For network information.
   Examples: <CMD>NETWORK: IP_LOOKUP</CMD>, <CMD>NETWORK: WEATHER</CMD>
7. TASK_COMPLETE: When all steps of a multi-step task are finished.
   Example: <CMD>TASK_COMPLETE: Opened Notepad and wrote the leave letter for you.</CMD>

IMPORTANT: Output ONLY the `<CMD>...</CMD>` tag for the next action step."""

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
            response_text = response.text if response.text else ""
            return response_text.strip()
        except Exception as e:
            log.warning(f"[Router Warning]: Online API failed ({e}). Falling back to Local Ollama...")
            return query_ollama(prompt=prompt, model=DEFAULT_MODEL)
    else:
        try:
            return query_ollama(prompt=prompt, model=DEFAULT_MODEL)
        except Exception as e:
            log.warning(f"[Router Warning]: Local Ollama failed ({e}). Falling back to Online API...")
            client = get_gemini_client()
            response = generate_with_retry(client, contents=[prompt], model=GEMINI_VISION_MODEL)
            response_text = response.text if response.text else ""
            return response_text.strip()

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
        
    log.info(f"[Fast Windows Finder]: Searching for '{cmd_target}' across Windows shortcuts...")
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
        log.info(f"[Resolved Windows Path]: {new_tag}")
        return new_tag
    return cmd_str

def process_statement(statement: str, is_sleeping: bool = False) -> tuple[str, bool, str | None]:
    """
    Processes user statement through Universal Dynamic State Machine Step Orchestrator Loop.
    Supports arbitrary multi-step sequences of commands, vision clicks, and typing.
    Returns (response_text, is_action_executed, new_state).
    """
    if not statement or not statement.strip():
        return "", False, None
        
    if is_sleeping:
        if any(w in statement.lower() for w in ["awake", "wake up", "come back"]):
            res = execute_action("ACTION_AWAKEN", statement)
            return res, True, "AWAKE"
        return "", False, "SLEEPING"
        
    requires_online = classify_requires_online(statement)
    log.info(f"[Intent Router]: User request '{statement}' routed to {'Online API' if requires_online else 'Local Model'}")
    
    # Universal step-by-step loop
    step_history = []
    max_steps = 8
    
    for step_num in range(1, max_steps + 1):
        history_str = "\n".join([f"Step {i+1}: {cmd} -> Result: {res}" for i, (cmd, res) in enumerate(step_history)])
        prompt = f"{UNIVERSAL_SYSTEM_PROMPT}\n\nUser Request: {statement}\n"
        if step_history:
            prompt += f"\nCompleted Step History:\n{history_str}\n\nEvaluate progress and output the single NEXT <CMD>...</CMD> tag (or <CMD>TASK_COMPLETE: summary</CMD> if finished)."
        else:
            prompt += "\nOutput the single initial <CMD>...</CMD> tag or direct conversational reply."
            
        llm_output = generate_model_response(prompt, use_online=requires_online)
        cmd_str = extract_command_tag(llm_output)
        
        # Legacy fallback handlers
        if not cmd_str:
            for legacy_act in ["ACTION_AWAKEN", "ACTION_SLEEP", "ACTION_APPEAR", "ACTION_EXIT"]:
                if legacy_act in llm_output:
                    cmd_str = legacy_act
                    break

        # If no command tag returned on initial step, treat as normal conversational reply
        if not cmd_str and not step_history:
            log.info(f"[Orchestrator]: Direct conversational response generated.")
            return llm_output, False, None
            
        # If no command tag on later step, treat output as completion response
        if not cmd_str and step_history:
            log.info(f"[Orchestrator]: Loop completed naturally after {len(step_history)} steps.")
            return llm_output, True, None

        # Check for TASK_COMPLETE tag
        if cmd_str.startswith("TASK_COMPLETE:"):
            summary = cmd_str.split("TASK_COMPLETE:", 1)[1].strip()
            log.info(f"[Orchestrator]: Task complete: {summary}")
            return summary, True, None

        log.info(f"[Orchestrator Step {step_num}]: Next Action Identified: {cmd_str}")
        
        # Self-correction retry loop inside each step execution
        max_retries = 2
        current_cmd = cmd_str
        step_success = False
        step_result = ""
        
        for attempt in range(max_retries + 1):
            try:
                current_cmd = resolve_windows_command(current_cmd, statement, requires_online)
                step_result = execute_action(current_cmd, statement)
                
                # Check immediate state transitions
                if current_cmd in ["SYSTEM: SLEEP", "ACTION_SLEEP"]:
                    return step_result, True, "SLEEPING"
                elif current_cmd in ["SYSTEM: EXIT", "ACTION_EXIT"]:
                    return "EXIT_APP", True, None
                    
                step_success = True
                break
            except Exception as e:
                err_msg = str(e)
                log.error(f"[Execution Error on Step {step_num}, attempt {attempt+1}]: {err_msg}")
                if attempt == max_retries:
                    step_result = f"Failed after {max_retries} attempts: {err_msg}"
                    break
                    
                log.info("[Triggering Self-Correction Retry Loop...]")
                retry_prompt = (
                    f"{UNIVERSAL_SYSTEM_PROMPT}\n\n"
                    f"Previous command `<CMD>{current_cmd}</CMD>` failed with error:\n{err_msg}\n"
                    f"Correct your mistake and output ONLY the valid executable `<CMD>...</CMD>` tag."
                )
                retry_output = generate_model_response(retry_prompt, use_online=requires_online)
                new_cmd = extract_command_tag(retry_output)
                if new_cmd:
                    current_cmd = new_cmd
                    log.info(f"[Self-Corrected Command]: {current_cmd}")

        step_history.append((current_cmd, step_result))
        time.sleep(0.5) # Brief pause for UI stability
        
        # If single one-shot action (like opening browser or weather), return early if no multi-step needed
        if not step_history or len(step_history) == 1:
            multi_keywords = ["and", "then", "after", "click", "write", "type"]
            if not any(kw in statement.lower() for kw in multi_keywords):
                return step_result, True, None

    final_summary = "\n".join([f"- {cmd}: {res}" for cmd, res in step_history])
    return f"Completed multi-step task:\n{final_summary}", True, None
