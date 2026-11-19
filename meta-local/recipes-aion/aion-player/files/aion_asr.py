"""Offline Mandarin transcription with the Vosk ARM64 C runtime."""

from ctypes import CDLL, c_char_p, c_float, c_int, c_void_p
import json
import os
from pathlib import Path
import re
import wave

LIBRARY = "/usr/lib/aion-vosk/libvosk.so"
MODEL = Path("/usr/share/aion-vosk/mandarin")


def transcribe(wav_path):
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

    with wave.open(str(wav_path), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
            raise ValueError("Expected mono 16-bit PCM at 16000 Hz")
        engine.vosk_set_log_level(-1)
        model = engine.vosk_model_new(os.fsencode(MODEL))
        if not model:
            raise OSError("Vosk Mandarin model could not load")
        try:
            recognizer = engine.vosk_recognizer_new(model, audio.getframerate())
            if not recognizer:
                raise OSError("Vosk recognizer could not start")
            try:
                parts = []
                while chunk := audio.readframes(4000):
                    result = engine.vosk_recognizer_accept_waveform(recognizer, chunk, len(chunk))
                    if result < 0:
                        raise OSError("Vosk could not decode audio")
                    if result == 1:
                        parts.append(json.loads(engine.vosk_recognizer_result(recognizer))["text"])
                parts.append(json.loads(engine.vosk_recognizer_final_result(recognizer))["text"])
            finally:
                engine.vosk_recognizer_free(recognizer)
        finally:
            engine.vosk_model_free(model)
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", " ".join(parts)).strip()
