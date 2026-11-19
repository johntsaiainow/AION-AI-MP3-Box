"""Continuous offline Mandarin voice input for the AION main page."""

from ctypes import CDLL, c_char_p, c_float, c_int, c_void_p
import array
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

LIBRARY = "/usr/lib/aion-vosk/libvosk.so"
MODEL = Path("/usr/share/aion-vosk/mandarin")
SAMPLE_RATE = 16000
BLOCK_FRAMES = 4000
SILENCE_THRESHOLD = 80
SILENCE_DURATION = 1.0

_audio_busy = threading.Event()
_listener_error = None
_microphone_rms = 0
_live_text = ""


def set_audio_busy(busy):
    if busy:
        _audio_busy.set()
    else:
        _audio_busy.clear()


class VoiceListener:
    def __init__(self):
        self.commands = queue.Queue()
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        if not Path(LIBRARY).is_file() or not MODEL.is_dir():
            return
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True,
                                       name="aion-voice-listener")
        self.thread.start()

    def stop(self):
        self.running = False

    def _engine(self):
        engine = CDLL(LIBRARY)
        signatures = {
            "vosk_set_log_level": (None, (c_int,)),
            "vosk_model_new": (c_void_p, (c_char_p,)),
            "vosk_model_free": (None, (c_void_p,)),
            "vosk_recognizer_new": (c_void_p, (c_void_p, c_float)),
            "vosk_recognizer_free": (None, (c_void_p,)),
            "vosk_recognizer_accept_waveform": (c_int, (c_void_p, c_char_p, c_int)),
            "vosk_recognizer_result": (c_char_p, (c_void_p,)),
            "vosk_recognizer_final_result": (c_char_p, (c_void_p,)),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(engine, name)
            function.restype = result
            function.argtypes = arguments
        engine.vosk_set_log_level(-1)
        model = engine.vosk_model_new(os.fsencode(MODEL))
        if not model:
            raise OSError("Vosk Mandarin model could not load")
        return engine, model

    def _listen_loop(self):
        global _listener_error, _microphone_rms, _live_text
        try:
            engine, model = self._engine()
        except Exception as exc:
            _listener_error = str(exc)
            return

        env = os.environ.copy()
        env.setdefault("PULSE_SERVER", "unix:/run/aion-pulse/pulse/native")
        env.setdefault("PULSE_COOKIE", "/var/lib/aion-audio/.config/pulse/cookie")

        try:
            while self.running:
                if _audio_busy.is_set():
                    time.sleep(0.1)
                    continue

                rec = engine.vosk_recognizer_new(model, float(SAMPLE_RATE))
                if not rec:
                    time.sleep(0.5)
                    continue

                process = None
                try:
                    process = subprocess.Popen([
                        "arecord", "-q", "-t", "raw", "-f", "S16_LE",
                        "-c", "1", "-r", str(SAMPLE_RATE), "-B", "250000"
                    ], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, env=env)

                    speaking = False
                    last_speech = time.monotonic()
                    while self.running:
                        if _audio_busy.is_set():
                            time.sleep(0.05)
                            continue
                        data = process.stdout.read(BLOCK_FRAMES * 2)
                        if not data:
                            break

                        samples = array.array("h")
                        samples.frombytes(data)
                        if os.sys.byteorder == "big":
                            samples.byteswap()
                        volume = sum(abs(value) for value in samples) / max(1, len(samples))
                        _microphone_rms = int(volume)

                        if volume > SILENCE_THRESHOLD:
                            if not speaking:
                                speaking = True
                            last_speech = time.monotonic()
                            engine.vosk_recognizer_accept_waveform(rec, data, len(data))
                            partial = json.loads(engine.vosk_recognizer_result(rec))
                            text = partial.get("partial", "").replace(" ", "").strip()
                            if text:
                                _live_text = text
                        elif speaking:
                            engine.vosk_recognizer_accept_waveform(rec, data, len(data))
                            if time.monotonic() - last_speech > SILENCE_DURATION:
                                break

                    if speaking:
                        payload = json.loads(engine.vosk_recognizer_final_result(rec))
                        text = payload.get("text", "").replace(" ", "").strip()
                        if text:
                            self.commands.put(text)
                            _live_text = text
                except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
                    time.sleep(0.2)
                finally:
                    engine.vosk_recognizer_free(rec)
                    if process is not None:
                        process.terminate()
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
        finally:
            engine.vosk_model_free(model)

    def microphone_status(self):
        filled = max(0, min(16, _microphone_rms // 16))
        bar = "█" * filled + "░" * (16 - filled)
        return f"麥克風 [{bar}] {_microphone_rms}"

    def live_text(self):
        return _live_text


_listener = VoiceListener()
_listener_enabled = False


def start_voice():
    global _listener_enabled
    _listener_enabled = True
    _listener.start()


def stop_voice():
    global _listener_enabled
    _listener_enabled = False
    _listener.stop()


def get_command():
    try:
        return _listener.commands.get_nowait()
    except queue.Empty:
        return None


def listener_status():
    if _listener_error:
        return "語音：異常 · " + _listener_error
    return "語音：監聽中" if _listener_enabled else "語音：關閉"
