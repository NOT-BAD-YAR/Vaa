import speech_recognition as sr
import pyttsx3

def speak(text: str):
    """Speaks the provided text using Windows SAPI5 voice engine."""
    try:
        engine = pyttsx3.init()
        # Set speech rate slightly faster or normal
        rate = engine.getProperty('rate')
        engine.setProperty('rate', rate - 10)
        
        # Select sweet female voice (Zira or Hazel)
        voices = engine.getProperty('voices')
        for voice in voices:
            if "zira" in voice.name.lower() or "hazel" in voice.name.lower() or "female" in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
                
        print(f"[Vaa]: {text}")
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"[Ivanae (TTS Error)]: {text} (Error: {e})")

def listen() -> str:
    """Listens to microphone audio and converts voice note to text."""
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("\n[Listening...] Speak now:")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            print("[Recognizing...]")
            text = recognizer.recognize_google(audio)
            print(f"[You said]: {text}")
            return text
    except sr.WaitTimeoutError:
        print("[No speech detected within timeout]")
        return ""
    except sr.UnknownValueError:
        print("[Could not understand speech]")
        return ""
    except Exception as e:
        print(f"[Microphone Error]: {e}")
        return ""
