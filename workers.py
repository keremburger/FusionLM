from PyQt6.QtCore import QThread, pyqtSignal
import ollama
import requests
from bs4 import BeautifulSoup

class ModelWorker(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal()
    err = pyqtSignal(str)

    def __init__(self, model, messages, **kwargs):
        super().__init__()
        self.model = model
        self.messages = messages
        self.kwargs = kwargs

    def run(self):
        try:
            stream = ollama.chat(model=self.model, messages=self.messages, stream=True, options=self.kwargs)
            for chunk in stream:
                self.chunk.emit(chunk['message']['content'])
            self.done.emit()
        except Exception as e:
            self.err.emit(str(e))

class MicWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, lang_code, wake_word=None):
        super().__init__()
        self.lang_code = lang_code
        self.wake_word = wake_word
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source)
                while self.is_running:
                    try:
                        if self.wake_word:
                            audio = r.listen(source, phrase_time_limit=3)
                            text = r.recognize_google(audio, language=self.lang_code).lower()
                            if self.wake_word.lower() in text:
                                audio = r.listen(source)
                                command = r.recognize_google(audio, language=self.lang_code)
                                self.finished.emit(command)
                                return
                        else:
                            audio = r.listen(source)
                            text = r.recognize_google(audio, language=self.lang_code)
                            self.finished.emit(text)
                            return
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError as e:
                        self.error.emit(f"Speech service error: {e}")
                        return
                    except Exception:
                        if self.is_running:
                            continue
        except ImportError:
            self.error.emit("SpeechRecognition not installed.")
        except Exception as e:
            self.error.emit(str(e))

class WebSearchThread(QThread):
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        # DuckDuckGo (önce yeni ddgs paketi, sonra eski duckduckgo_search)
        try:
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(self.query, max_results=5))
                if results:
                    self.result.emit([f"{r['title']}: {r['body']}" for r in results])
                    return
            except ImportError:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(self.query, max_results=5))
                if results:
                    self.result.emit([f"{r['title']}: {r['body']}" for r in results])
                    return
        except Exception:
            pass
        # Fallback Bing
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(f"https://www.bing.com/search?q={self.query}", headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            snippets = []
            for result in soup.select('.b_algo'):
                title = result.select_one('h2')
                desc = result.select_one('.b_caption p')
                if title and desc:
                    snippets.append(f"{title.get_text()}: {desc.get_text()}")
            if snippets:
                self.result.emit(snippets[:5])
                return
        except Exception:
            pass
        self.error.emit("No search results found.")