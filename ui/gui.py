import os
import sys
import queue
import threading
import customtkinter as ctk

# Ensure src modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.speech import listen, speak
from src.assistant import process_statement

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class VaaGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Vaa - Windows Voice Assistant")
        self.geometry("750x650")
        self.minsize(600, 500)
        
        self.is_sleeping = False
        self.is_listening = False
        self.listening_thread = None
        self.msg_queue = queue.Queue()
        
        self._setup_ui()
        self._start_queue_listener()
        
        # Initial greeting
        greeting = "Hi ticko Im your mario by the way your personal assistant today what we are gonna do soldra dei lavadae ...!"
        self._log_message("Vaa", greeting)
        self._run_async(lambda: speak(greeting))

    def _setup_ui(self):
        # Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=10)
        header_frame.pack(padx=15, pady=(15, 10), fill="x")
        
        title_label = ctk.CTkLabel(
            header_frame, 
            text="⚡ Vaa Assistant", 
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left", padx=15, pady=15)
        
        self.status_label = ctk.CTkLabel(
            header_frame, 
            text="🟢 Awake - Idle", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#2ecc71"
        )
        self.status_label.pack(side="right", padx=15, pady=15)
        
        # Chat Display
        self.chat_box = ctk.CTkTextbox(self, font=ctk.CTkFont(size=14), wrap="word", corner_radius=10)
        self.chat_box.pack(padx=15, pady=5, fill="both", expand=True)
        self.chat_box.configure(state="disabled")
        
        # Input Controls Frame
        input_frame = ctk.CTkFrame(self, corner_radius=10)
        input_frame.pack(padx=15, pady=(10, 5), fill="x")
        
        self.entry = ctk.CTkEntry(
            input_frame, 
            placeholder_text="Type a command or ask a question...", 
            font=ctk.CTkFont(size=14)
        )
        self.entry.pack(side="left", padx=(15, 10), pady=12, fill="x", expand=True)
        self.entry.bind("<Return>", lambda event: self._on_send_text())
        
        send_btn = ctk.CTkButton(
            input_frame, 
            text="Send 📤", 
            width=90, 
            command=self._on_send_text
        )
        send_btn.pack(side="right", padx=(0, 15), pady=12)
        
        # Action Buttons Frame
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(padx=15, pady=(5, 15), fill="x")
        
        self.voice_btn = ctk.CTkButton(
            btn_frame, 
            text="🎤 Start Voice Mode", 
            fg_color="#3498db", 
            hover_color="#2980b9",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_voice_mode
        )
        self.voice_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.sleep_btn = ctk.CTkButton(
            btn_frame, 
            text="💤 Put to Sleep", 
            fg_color="#e67e22", 
            hover_color="#d35400",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_sleep
        )
        self.sleep_btn.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def _start_queue_listener(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "LOG":
                    sender, text = data
                    self._log_message(sender, text)
                elif msg_type == "STATUS":
                    status_text, color = data
                    self.status_label.configure(text=status_text, text_color=color)
                elif msg_type == "SLEEP_STATE":
                    self.is_sleeping = data
                    if self.is_sleeping:
                        self.sleep_btn.configure(text="🟢 Wake Up", fg_color="#2ecc71", hover_color="#27ae60")
                        self.status_label.configure(text="💤 Sleeping", text_color="#f39c12")
                    else:
                        self.sleep_btn.configure(text="💤 Put to Sleep", fg_color="#e67e22", hover_color="#d35400")
                        self.status_label.configure(text="🟢 Awake - Idle", text_color="#2ecc71")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._start_queue_listener)

    def _log_message(self, sender: str, text: str):
        self.chat_box.configure(state="normal")
        formatted = f"[{sender}]: {text}\n\n"
        self.chat_box.insert("end", formatted)
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _run_async(self, target_fn):
        threading.Thread(target=target_fn, daemon=True).start()

    def _on_send_text(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._log_message("You", text)
        
        self.msg_queue.put(("STATUS", ("🤖 Processing...", "#f1c40f")))
        self._run_async(lambda: self._process_statement_worker(text))

    def _toggle_sleep(self):
        if self.is_sleeping:
            self._log_message("You", "awake")
            self._run_async(lambda: self._process_statement_worker("awake"))
        else:
            self._log_message("You", "call Hibernate yourself")
            self._run_async(lambda: self._process_statement_worker("call Hibernate yourself"))

    def _toggle_voice_mode(self):
        if self.is_listening:
            self.is_listening = False
            self.voice_btn.configure(text="🎤 Start Voice Mode", fg_color="#3498db", hover_color="#2980b9")
            self.msg_queue.put(("STATUS", ("🟢 Awake - Idle" if not self.is_sleeping else "💤 Sleeping", "#2ecc71" if not self.is_sleeping else "#f39c12")))
        else:
            self.is_listening = True
            self.voice_btn.configure(text="🛑 Stop Voice Mode", fg_color="#e74c3c", hover_color="#c0392b")
            self._run_async(self._continuous_listen_worker)

    def _continuous_listen_worker(self):
        while self.is_listening:
            self.msg_queue.put(("STATUS", ("👂 Listening...", "#3498db")))
            statement = listen()
            if not self.is_listening:
                break
            if statement:
                self.msg_queue.put(("LOG", ("You (Voice)", statement)))
                self.msg_queue.put(("STATUS", ("🤖 Processing...", "#f1c40f")))
                self._process_statement_worker(statement)
            else:
                self.msg_queue.put(("STATUS", ("🟢 Awake - Idle" if not self.is_sleeping else "💤 Sleeping", "#2ecc71" if not self.is_sleeping else "#f39c12")))

    def _process_statement_worker(self, statement: str):
        try:
            response, is_action, new_state = process_statement(statement, is_sleeping=self.is_sleeping)
            
            if new_state == "SLEEPING":
                self.msg_queue.put(("SLEEP_STATE", True))
            elif new_state == "AWAKE":
                self.msg_queue.put(("SLEEP_STATE", False))
                
            if response == "EXIT_APP":
                self.msg_queue.put(("LOG", ("Vaa", "Goodbye! Closing Vaa...")))
                speak("Goodbye!")
                self.quit()
                return
                
            if response:
                self.msg_queue.put(("LOG", ("Vaa", response)))
                speak(response)
                
            if not self.is_listening:
                status_text = "💤 Sleeping" if self.is_sleeping else "🟢 Awake - Idle"
                color = "#f39c12" if self.is_sleeping else "#2ecc71"
                self.msg_queue.put(("STATUS", (status_text, color)))
        except Exception as e:
            self.msg_queue.put(("LOG", ("System Error", str(e))))
            if not self.is_listening:
                self.msg_queue.put(("STATUS", ("⚠️ Error", "#e74c3c")))

if __name__ == "__main__":
    app = VaaGUI()
    app.mainloop()
