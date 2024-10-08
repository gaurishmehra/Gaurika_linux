import requests
import playsound
import os
from typing import Union
import threading
import pyaudio
import wave
from groq import Groq
import logging
from dotenv import load_dotenv

load_dotenv()

# Suppress ALSA warnings using logging
logging.getLogger('alsaaudio').setLevel(logging.CRITICAL)

def listen():
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Audio recording parameters
    CHUNK = 4096  # Increased chunk size for faster processing
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100

    recording = False
    frames = []
    transcription_text = ""

    def record_audio():
        nonlocal frames
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        frames = []
        while recording:
            data = stream.read(CHUNK)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        # Save the recorded audio to a file
        filename = "recorded_audio.wav"
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        return filename

    def transcribe_audio(filename):
        nonlocal transcription_text
        with open(filename, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filename, file),
                model="whisper-large-v3",
                prompt="Specify context or spelling",
                response_format="json",
                language="en",
                temperature=0.0
            )
        print("Transcription:", transcription.text.strip())

        # Clean up the temporary audio file
        os.remove(filename)
        transcription_text = transcription.text.strip()
        return transcription_text

    def wait_for_input():
        nonlocal recording
        input("Press Enter to start recording...")
        recording = True
        print("Recording started. Press Enter again to stop...")
        input()
        recording = False
        print("Recording stopped. Transcribing...")

    # Start input thread
    input_thread = threading.Thread(target=wait_for_input)
    input_thread.start()

    while True:
        if recording:
            # Start recording in a separate thread
            record_thread = threading.Thread(target=record_audio)
            record_thread.start()

            # Wait for the recording to finish
            input_thread.join()
            record_thread.join()

            # Transcribe the audio
            audio_file = "recorded_audio.wav"
            if os.path.exists(audio_file):
                transcribe_audio(audio_file)
            else:
                print("No audio recorded.")
            break

    return transcription_text

def generate_audio(message: str, voice: str = "Salli"):
    url = f"https://api.streamelements.com/kappa/v2/speech?voice={voice}&text={{{message}}}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    try:
        return requests.get(url=url, headers=headers).content
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None

def speak(message: str, folder: str = "", extension: str = ".mp3") -> Union[None, str]:
    try:
        result_content = generate_audio(message)
        if result_content:
            file_path = os.path.join(folder, f"Audio{extension}")
            with open(file_path, "wb") as file:
                file.write(result_content)
            playsound.playsound(file_path)
            os.remove(file_path)
        return None
    except Exception as e:
        return f"Error playing TTS: {str(e)}"
    