import sys
import threading
import time
import requests
import json
import nltk
from datetime import datetime
from queue import Queue

import speech_recognition as sr
import pyttsx3

from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QComboBox, QTextEdit, QVBoxLayout, QHBoxLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QIcon

# Ensure NLTK data is downloaded
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

class LogHandler(QObject):
    new_log = pyqtSignal(str)

class VirtualAssistant:
    def __init__(self, device_index=None, log_handler=None):
        # Initialize the recognizer and the microphone
        self.recognizer = sr.Recognizer()
        try:
            if device_index is not None:
                self.microphone = sr.Microphone(device_index=device_index)
            else:
                self.microphone = sr.Microphone()
        except Exception as e:
            self.log(f"Microphone initialization failed: {e}")
            return

        # Initialize the speech engine
        self.engine = pyttsx3.init()
        voices = self.engine.getProperty('voices')
        if len(voices) > 1:
            self.engine.setProperty('voice', voices[1].id)  # Choose voice
        else:
            self.engine.setProperty('voice', voices[0].id)
        self.engine.setProperty('rate', 155)  # Speech rate

        self.log_handler = log_handler
        self.log = self.log_handler.new_log.emit

        # Initialize the speech queue and thread
        self.speech_queue = Queue()
        self.speech_thread = threading.Thread(target=self.process_speech_queue)
        self.speech_thread.start()

        # Event to control speaking/listening
        self.is_speaking = threading.Event()
        self.is_listening = threading.Event()

        # Assistant state
        self.listening = True  # Corrected: Set to True

        # Lock for synchronization
        self.listen_lock = threading.Lock()

        # Start listening thread
        self.listen_thread = threading.Thread(target=self.listen)
        self.listen_thread.start()

        # Greeting
        self.speak("Hello! I am your virtual assistant. Press the 'Listen' button to ask a question.")

    def process_speech_queue(self):
        while True:
            text = self.speech_queue.get()
            if text is None:
                self.log("Speech thread exiting.")
                break  # Exit the thread
            self.is_speaking.set()  # Signal that speaking has started
            self.log(f"Assistant is speaking: {text}")
            self.engine.say(text)
            self.engine.runAndWait()
            self.is_speaking.clear()  # Signal that speaking has finished
            self.speech_queue.task_done()

    def speak(self, text):
        """Enqueue text to be spoken."""
        self.speech_queue.put(text)

    def start_listening(self):
        """Signal the assistant to start listening."""
        with self.listen_lock:
            if not self.is_listening.is_set():
                self.is_listening.set()
                self.log("Listening started.")

    def stop_listening(self):
        """Signal the assistant to stop listening."""
        with self.listen_lock:
            if self.is_listening.is_set():
                self.is_listening.clear()
                self.log("Listening stopped.")

    def listen(self):
        """Wait for the listen signal and process audio when received."""
        self.log("Listening thread started.")
        while True:
            self.is_listening.wait()  # Wait until listening is enabled
            if not self.listening:
                break  # Exit if assistant is shutting down
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    self.log("Listening for input...")
                    audio = self.recognizer.listen(source, timeout=5)
                try:
                    command = self.recognizer.recognize_google(audio)
                    self.log(f"You said: {command}")
                    self.process_command(command.lower())
                except sr.UnknownValueError:
                    self.speak("I'm sorry, I didn't catch that.")
                except sr.RequestError as e:
                    self.speak("Could not request results; check your network connection.")
                    self.log(f"RequestError: {e}")
                finally:
                    self.stop_listening()
            except sr.WaitTimeoutError:
                self.log("Listening timed out while waiting for speech")
                self.speak("Listening timed out, please try again.")
                self.stop_listening()
            except Exception as e:
                self.log(f"An unexpected error occurred in listen(): {e}")
                self.speak("An error occurred. Please try again.")
                self.stop_listening()

    def process_command(self, command):
        """Process the voice command."""
        self.log(f"Processing command: {command}")
        tokens = word_tokenize(command)
        tokens = [word for word in tokens if word.lower() not in stopwords.words('english')]

        if "weather" in tokens:
            self.get_weather()
        elif "time" in tokens:
            self.tell_time()
        elif "news" in tokens:
            self.get_news()
        elif any(word in tokens for word in ["stop", "exit", "quit"]):
            self.exit_program()
        elif any(greeting in tokens for greeting in ["hi", "hello", "hey"]):
            self.speak("Hello! How can I assist you?")
        elif any(word in tokens for word in ["how", "are", "you"]):
            self.speak("I'm doing well, thank you!")
        else:
            self.speak("I'm sorry, I can't perform that action yet.")

    def get_weather(self):
        """Fetch and speak the current weather."""
        api_key = "7643d76b3c5b557d2177eb82a2421c68"  # Replace with your OpenWeatherMap API key
        city = "Phoenix"  # Replace with your city
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"

        try:
            response = requests.get(url)
            data = response.json()

            if data["cod"] != 200:
                self.speak("I'm sorry, I couldn't retrieve the weather information.")
                return

            weather = data["weather"][0]["description"]
            temperature = data["main"]["temp"]
            response_text = f"The current weather in {city} is {weather} with a temperature of {temperature} degrees Celsius."
            self.speak(response_text)

        except Exception as e:
            self.speak("I'm sorry, there was an error getting the weather information.")
            self.log(f"Weather Error: {e}")

    def tell_time(self):
        """Tell the current time."""
        now = datetime.now()
        current_time = now.strftime("%I:%M %p")
        self.speak(f"The current time is {current_time}.")

    def get_news(self):
        """Fetch and speak the latest news headlines."""
        api_key = "a1bd3f8453bd417d9ad5c810139b0c29"  # Replace with your NewsAPI API key
        url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={api_key}"

        try:
            response = requests.get(url)
            data = response.json()

            if data["status"] != "ok":
                self.speak("I'm sorry, I couldn't retrieve the news.")
                return

            articles = data["articles"][:5]
            self.speak("Here are the top news headlines:")
            for article in articles:
                self.speak(article["title"])

        except Exception as e:
            self.speak("I'm sorry, there was an error getting the news.")
            self.log(f"News Error: {e}")

    def exit_program(self):
        """Exit the program gracefully."""
        self.speak("Goodbye!")
        self.listening = False
        self.is_listening.set()  # Unblock the listen thread if waiting
        if self.listen_thread.is_alive():
            self.listen_thread.join()
        self.speech_queue.put(None)
        if self.speech_thread.is_alive():
            self.speech_thread.join()
        self.engine.stop()
        self.log("Assistant exited.")
        sys.exit(0)

def main():
    app = QApplication(sys.argv)

    # Create main window
    window = QWidget()
    window.setWindowTitle("Virtual Assistant")
    window.setGeometry(100, 100, 600, 400)
    window.setWindowIcon(QIcon('assistant_icon.png'))  # Optional: Set an icon

    # Create log handler
    log_handler = LogHandler()

    # Create GUI elements
    mic_label = QLabel("Select Microphone:")
    mic_combo = QComboBox()

    # List available microphones
    mic_names = sr.Microphone.list_microphone_names()
    mic_combo.addItems(mic_names)

    start_button = QPushButton("Start Assistant")
    listen_button = QPushButton("Listen")
    listen_button.setEnabled(False)  # Disabled until assistant starts
    log_area = QTextEdit()
    log_area.setReadOnly(True)

    # Layouts
    h_layout = QHBoxLayout()
    h_layout.addWidget(mic_label)
    h_layout.addWidget(mic_combo)
    h_layout.addWidget(start_button)
    h_layout.addWidget(listen_button)

    v_layout = QVBoxLayout()
    v_layout.addLayout(h_layout)
    v_layout.addWidget(log_area)

    window.setLayout(v_layout)
    window.show()

    # Function to log messages to the text area
    def log_message(message):
        log_area.append(message)
        log_area.verticalScrollBar().setValue(log_area.verticalScrollBar().maximum())

    log_handler.new_log.connect(log_message)

    # Assistant instance placeholder
    assistant_instance = None

    # Function to start the assistant
    def start_assistant():
        nonlocal assistant_instance
        mic_index = mic_combo.currentIndex()
        log_message(f"Starting assistant with microphone index {mic_index}")
        assistant_instance = VirtualAssistant(device_index=mic_index, log_handler=log_handler)
        start_button.setEnabled(False)
        listen_button.setEnabled(True)

    # Function to toggle listening
    def toggle_listening():
        if assistant_instance:
            if not assistant_instance.is_listening.is_set():
                # Start listening
                assistant_instance.start_listening()
                listen_button.setText("Stop Listening")
            else:
                # Stop listening
                assistant_instance.stop_listening()
                listen_button.setText("Listen")

    start_button.clicked.connect(start_assistant)
    listen_button.clicked.connect(toggle_listening)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()