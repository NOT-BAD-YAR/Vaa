import sys
from src.speech import listen, speak
from src.assistant import process_statement

def main():
    # By default open GUI unless explicitly passed 'text' or 'voice' argument
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["voice", "-v", "--voice"]:
            print("[Launching CLI Voice Mode...]")
            use_voice = True
        elif arg in ["text", "-t", "--text"]:
            print("[Launching CLI Text Mode...]")
            use_voice = False
        else:
            print(f"Unknown argument '{arg}'. Launching GUI by default...")
            from ui.gui import VaaGUI
            app = VaaGUI()
            app.mainloop()
            return
    else:
        print("[Launching Desktop GUI by default...]")
        from ui.gui import VaaGUI
        app = VaaGUI()
        app.mainloop()
        return
    is_sleeping = False
    
    speak("Hi daaaa lavadaeeeeeee ...!")
    
    while True:
        try:
            if use_voice:
                statement = listen()
                if not statement:
                    # Fallback or retry prompt
                    print("Press Enter to listen again, or type 't' to switch to Text mode, 'q' to quit.")
                    user_cmd = input("> ").strip().lower()
                    if user_cmd == 'q':
                        break
                    elif user_cmd == 't':
                        use_voice = False
                        print("[Switched to Text Mode]")
                    continue
            else:
                statement = input("\n[You]: ").strip()
                if statement.lower() in ['q', 'quit', 'exit']:
                    break
                    
            if not statement:
                continue
                
            response, is_action, new_state = process_statement(statement, is_sleeping=is_sleeping)
            
            if new_state == "SLEEPING":
                is_sleeping = True
            elif new_state == "AWAKE":
                is_sleeping = False
                
            if response == "EXIT_APP":
                speak("Goodbye!")
                break
                
            if response:
                speak(response)
                
        except KeyboardInterrupt:
            print("\nExiting Vaa...")
            break
        except Exception as e:
            print(f"\n[Error]: {e}")
            
if __name__ == "__main__":
    main()
