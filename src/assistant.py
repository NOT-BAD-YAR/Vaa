from src.config import DEFAULT_MODEL, query_ollama
from src.actions import execute_action

BASE_PROMPT = """You are a virtual assistant that can identify actions based on a statement. If a suitable action is found respond with action name only. If no suitable action can be identified do not say things like I cannot perform action etc, instead respond to the statement normally as if it were a normal conversation and not a command. List of available actions are:
ACTION_AWAKEN, ACTION_SLEEP, ACTION_APPEAR, ACTION_EXIT, ACTION_OPEN_NOTEPAD, ACTION_OPEN_WORD, ACTION_OPEN_EXCEL, ACTION_OPEN_POWERPOINT, ACTION_OPEN_COMMAND_PROMPT, ACTION_OPEN_CAMERA, ACTION_OPEN_CALCULATOR, ACTION_FIND_MY_IP, ACTION_OPEN_YOUTUBE, ACTION_CHECK_WEATHER, ACTION_TAKE_SCREENSHOT, ACTION_START_SCREEN_RECORDING, ACTION_STOP_SCREEN_RECORDING, ACTION_MINIMIZE_DISAPPEAR_APPLICATION, ACTION_OPEN_BROWSER_WEBSITE, ACTION_WHAT_DO_YOU_SEE_IN_CAMERA"""

AVAILABLE_ACTIONS = {
    "ACTION_AWAKEN", "ACTION_SLEEP", "ACTION_APPEAR", "ACTION_EXIT",
    "ACTION_OPEN_NOTEPAD", "ACTION_OPEN_WORD", "ACTION_OPEN_EXCEL",
    "ACTION_OPEN_POWERPOINT", "ACTION_OPEN_COMMAND_PROMPT", "ACTION_OPEN_CAMERA",
    "ACTION_OPEN_CALCULATOR", "ACTION_FIND_MY_IP", "ACTION_OPEN_YOUTUBE",
    "ACTION_CHECK_WEATHER", "ACTION_TAKE_SCREENSHOT", "ACTION_START_SCREEN_RECORDING",
    "ACTION_STOP_SCREEN_RECORDING", "ACTION_MINIMIZE_DISAPPEAR_APPLICATION",
    "ACTION_OPEN_BROWSER_WEBSITE", "ACTION_WHAT_DO_YOU_SEE_IN_CAMERA"
}

def process_statement(statement: str, is_sleeping: bool = False) -> tuple[str, bool, str]:
    """
    Sends statement to local Ollama. Returns (response_text, is_action_executed, new_state).
    new_state can be "SLEEPING", "AWAKE", or None.
    """
    if not statement or not statement.strip():
        return "", False, None
        
    # Check simple local wake keywords if sleeping
    if is_sleeping and any(w in statement.lower() for w in ["awake", "wake up", "come back"]):
        return execute_action("ACTION_AWAKEN", statement), True, "AWAKE"
        
    full_prompt = f"{BASE_PROMPT}\n\nUser statement: {statement}"
    
    llm_output = query_ollama(prompt=full_prompt, model=DEFAULT_MODEL)
    
    # Check if the output contains or exactly matches one of our action tags
    for action in AVAILABLE_ACTIONS:
        if action in llm_output:
            if is_sleeping:
                if action in ["ACTION_AWAKEN", "ACTION_APPEAR"]:
                    print(f"[Identified Wake Action]: {action}")
                    return execute_action(action, statement), True, "AWAKE"
                else:
                    print(f"[Ignored Action (Sleeping)]: {action}")
                    return "", False, "SLEEPING"
            else:
                print(f"[Identified Action]: {action}")
                result = execute_action(action, statement)
                new_state = "SLEEPING" if action == "ACTION_SLEEP" else None
                return result, True, new_state
            
    # If no action identified and we are sleeping, stay silent
    if is_sleeping:
        return "", False, "SLEEPING"
        
    # If no action identified and awake, return normal conversation response
    return llm_output, False, None
