import sys
import re
import pyautogui
import time

def parse_and_click(coord_input: str):
    """
    Parses coordinate strings in various formats and performs a click.
    Supported formats:
      - "(x: 1050, y: 20)" or "x=1050 y=20"
      - "1050, 20" or "(1050, 20)" or "[1050, 20]"
      - Bounding box "[ymin, xmin, ymax, xmax]" or "[x1, y1, x2, y2]" (clicks center)
    """
    coord_input = coord_input.strip()
    screen_width, screen_height = pyautogui.size()
    
    target_x = None
    target_y = None
    
    # Format 1: Explicit x and y labels, e.g. "(x: 1050, y: 20)" or "x=1050, y=20"
    match_xy = re.search(r"x\s*[:=]\s*([0-9.]+).*?y\s*[:=]\s*([0-9.]+)", coord_input, re.IGNORECASE)
    if not match_xy:
        # Also check "y: ..., x: ..." just in case
        match_yx = re.search(r"y\s*[:=]\s*([0-9.]+).*?x\s*[:=]\s*([0-9.]+)", coord_input, re.IGNORECASE)
        if match_yx:
            target_y, target_x = float(match_yx.group(1)), float(match_yx.group(2))
    else:
        target_x, target_y = float(match_xy.group(1)), float(match_xy.group(2))
        
    # Format 2: 4-value bounding box [val1, val2, val3, val4]
    if target_x is None or target_y is None:
        match_box = re.search(r"\[?\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]?", coord_input)
        if match_box:
            c1, c2, c3, c4 = [float(val) for val in match_box.groups()]
            # Check if normalized <= 1.0 or <= 1000
            if all(c <= 1.0 for c in (c1, c2, c3, c4)):
                c1, c2, c3, c4 = c1 * screen_height, c2 * screen_width, c3 * screen_height, c4 * screen_width
            elif all(c <= 1000.0 for c in (c1, c2, c3, c4)) and any(c < 1000 for c in (c1, c2, c3, c4)):
                # Qwen 1000-scale [ymin, xmin, ymax, xmax]
                c1, c2, c3, c4 = (c1/1000.0)*screen_height, (c2/1000.0)*screen_width, (c3/1000.0)*screen_height, (c4/1000.0)*screen_width
            
            ymin, xmin, ymax, xmax = min(c1, c3), min(c2, c4), max(c1, c3), max(c2, c4)
            target_x = (xmin + xmax) / 2.0
            target_y = (ymin + ymax) / 2.0

    # Format 3: Simple 2-value coordinate pair (x, y) or [x, y] or x, y
    if target_x is None or target_y is None:
        match_pair = re.search(r"[\(\[\s]*([0-9]+)\s*[,x\s]\s*([0-9]+)[\)\]\s]*", coord_input)
        if match_pair:
            target_x, target_y = float(match_pair.group(1)), float(match_pair.group(2))
            
    if target_x is None or target_y is None:
        print(f"❌ Could not extract coordinates from input: '{coord_input}'")
        return False
        
    target_x = max(0, min(int(round(target_x)), screen_width - 1))
    target_y = max(0, min(int(round(target_y)), screen_height - 1))
    
    print(f"🎯 Coordinates resolved to: X={target_x}, Y={target_y}")
    print(f"🖱️ Moving mouse and clicking at ({target_x}, {target_y})...")
    pyautogui.moveTo(target_x, target_y, duration=0.4)
    pyautogui.click()
    print("✅ Clicked!")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If passed as command line argument (e.g. python click_coords.py 1050 20 or python click_coords.py "(x: 1050, y: 20)")
        input_str = " ".join(sys.argv[1:])
        parse_and_click(input_str)
    else:
        print("--- Coordinate Clicker ---")
        print(f"Screen resolution: {pyautogui.size()[0]}x{pyautogui.size()[1]}")
        while True:
            try:
                user_input = input("\nEnter coordinates to click (or 'q' to quit): ").strip()
                if user_input.lower() in ('q', 'quit', 'exit'):
                    break
                if user_input:
                    parse_and_click(user_input)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
