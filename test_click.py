import sys
import pyautogui
import time

def main():
    print("=========================================")
    print("    🖱️  X/Y Coordinate Click Tester  ")
    print("=========================================")
    screen_w, screen_h = pyautogui.size()
    print(f"Screen Resolution: {screen_w} x {screen_h}")
    print("Enter 'q' at any prompt to quit.\n")

    while True:
        try:
            user_input = input("Enter coordinates as 'X, Y' (or press Enter to input separately): ").strip()
            if user_input.lower() in ('q', 'quit', 'exit'):
                print("Exiting tester.")
                break
                
            x_val, y_val = None, None
            
            if "," in user_input or " " in user_input:
                parts = [p.strip() for p in user_input.replace(",", " ").split() if p.strip()]
                if len(parts) >= 2:
                    x_val, y_val = float(parts[0]), float(parts[1])
            
            if x_val is None or y_val is None:
                x_str = input("Enter X coordinate: ").strip()
                if x_str.lower() in ('q', 'quit', 'exit'):
                    break
                y_str = input("Enter Y coordinate: ").strip()
                if y_str.lower() in ('q', 'quit', 'exit'):
                    break
                x_val = float(x_str)
                y_val = float(y_str)
                
            # Clamping within screen boundaries
            safe_x = max(0, min(int(round(x_val)), screen_w - 1))
            safe_y = max(0, min(int(round(y_val)), screen_h - 1))
            
            print(f"\n🚀 Moving mouse to ({safe_x}, {safe_y})...")
            pyautogui.moveTo(safe_x, safe_y, duration=0.5)
            print(f"🖱️ Clicking at ({safe_x}, {safe_y})...")
            pyautogui.click()
            print("✅ Click executed!\n-----------------------------------------")
            
        except ValueError:
            print("❌ Invalid number entered. Please enter numbers like 500 or 120.5\n")
        except KeyboardInterrupt:
            print("\nExiting tester.")
            break
        except Exception as e:
            print(f"Error: {e}\n")

if __name__ == "__main__":
    main()
