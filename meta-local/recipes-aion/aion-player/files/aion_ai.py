"""Text and Mandarin voice interactions with a configured AI endpoint."""

from getpass import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import aion_asr
from aion_ui import options, screen, selection, tr

MAX_RESPONSE = 256 * 1024
MAX_SPEECH = 4 * 1024 * 1024


class AIError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def config_path(mode):
    directory = Path(os.environ.get("AION_AI_CONFIG_DIR", "/var/lib/aion-ai"))
    return directory / f"{mode}.json"


def endpoint_url(base_url, mode, api_key, route="/chat/completions"):
    if any(not char.isprintable() or char.isspace() for char in base_url):
        raise AIError(tr("Enter a valid API base URL.", "請輸入有效的 API 基礎網址。"))
    try:
        parts = urlsplit(base_url)
    except ValueError as exc:
        raise AIError(tr("Enter a valid API base URL.", "請輸入有效的 API 基礎網址。")) from exc
    if (
        parts.scheme not in ("http", "https") or not parts.hostname
        or parts.username is not None or parts.password is not None
        or "?" in base_url or "#" in base_url
    ):
        raise AIError(tr("Enter a valid API base URL.", "請輸入有效的 API 基礎網址。"))
    if parts.scheme != "https" and (mode == "cloud" or api_key):
        raise AIError(tr("Cloud connections and API keys require HTTPS.", "雲端連線和 API 金鑰須使用 HTTPS。"))
    base = base_url.rstrip("/")
    return base.removesuffix("/chat/completions") + route


def configure(mode, saved):
    example = "http://192.168.1.10:11434/v1" if mode == "local" else "https://api.example.com/v1"
    if not saved:
        print(f"{tr('Example', '範例')} · {example}")
    base_url = input(f"{tr('API base URL', 'API 基礎網址')} [{saved.get('url', '')}]: ").strip()
    base_url = base_url or saved.get("url", "")
    model = input(f"{tr('Model', '模型')} [{saved.get('model', '')}]: ").strip()
    model = model or saved.get("model", "")
    if not model:
        raise AIError(tr("Enter a model name.", "請輸入模型名稱。"))
    api_key = getpass(tr(
        "API key (Enter to keep, - to clear): ",
        "API 金鑰（按 Enter 保留，輸入 - 清除）：",
    )).strip()
    api_key = "" if api_key == "-" else api_key or saved.get("key", "")
    endpoint_url(base_url, mode, api_key)
    save_connection(mode, {**saved, "url": base_url, "model": model, "key": api_key})


def save_connection(mode, config, *, announce=True):
    path = config_path(mode)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(config, stream)
            stream.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if announce:
        print(tr("AI connection saved.", "AI 連線已儲存。"))


def post(mode, config, route, data, *, limit=MAX_RESPONSE):
    url = endpoint_url(config["url"], mode, config["key"], route)
    data = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config["key"]:
        headers["Authorization"] = "Bearer " + config["key"]
    request = Request(url, data=data, headers=headers, method="POST")
    opener = build_opener(NoRedirect(), ProxyHandler({})) if mode == "local" else build_opener(NoRedirect())
    with opener.open(request, timeout=45) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise AIError(tr("The AI response is too large.", "AI 回覆超過大小限制。"))
    return payload


def ask(mode, config, message, *, instructions=None):
    messages = [{"role": "user", "content": message}]
    if instructions:
        messages.insert(0, {"role": "system", "content": instructions})
    payload = post(mode, config, "/chat/completions", {
        "model": config["model"], "messages": messages, "stream": False,
    })
    try:
        content = json.loads(payload)["choices"][0]["message"]["content"]
    except (IndexError, KeyError, TypeError, ValueError):
        content = None
    if not isinstance(content, str) or not content.strip():
        raise AIError(tr("The service returned no text reply.", "服務未傳回文字回覆。"))
    return terminal_text(content)


def terminal_text(content):
    return "".join(char for char in content if char.isprintable() or char in "\n\t")


def configure_voice(mode, config):
    voice_settings = {}
    for key, label in (
        ("speech_model", tr("Speech model", "語音合成模型")),
        ("voice", tr("Voice name", "聲音名稱")),
    ):
        current = config.get(key, "")
        value = input(f"{label} [{current}]: ").strip() or current
        if not value:
            raise AIError(tr("Enter all voice settings.", "請填寫所有語音設定。"))
        voice_settings[key] = value
    save_connection(mode, {**config, **voice_settings})


def listen_mandarin():
    if not Path(aion_asr.LIBRARY).is_file() or not aion_asr.MODEL.is_dir():
        raise AIError(tr("The offline Mandarin model is not installed.", "尚未安裝離線中文模型。"))
    if input(tr("Press Enter to record for 8 seconds, or type anything to cancel: ",
                "按 Enter 錄音 8 秒，或輸入文字取消：")):
        return ""

    with tempfile.TemporaryDirectory(prefix="aion-voice-") as work:
        question = Path(work) / "question.wav"
        print(tr("Recording… Speak Mandarin now.", "錄音中…請說中文。"), flush=True)
        try:
            subprocess.run(
                ["arecord", "-q", "-d", "8", "-t", "wav", "-f", "S16_LE",
                 "-c", "1", "-r", "16000", str(question)],
                stdin=subprocess.DEVNULL, check=True, timeout=12,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AIError(tr("Could not record from the microphone.", "無法從麥克風錄音。")) from exc

        print(tr("Transcribing on the Pi…", "正在 Pi 上辨識語音…"), flush=True)
        try:
            text = terminal_text(aion_asr.transcribe(question)).strip()
        except (OSError, ValueError, EOFError, wave.Error) as exc:
            raise AIError(tr("Offline speech recognition failed.", "離線語音辨識失敗。")) from exc
    if not text:
        raise AIError(tr("No speech was recognized.", "未辨識到語音。"))
    print(f"{tr('You said', '你說')} · {text}")
    return text


def voice_turn(mode, config):
    if not all(isinstance(config.get(key), str) and config[key]
               for key in ("speech_model", "voice")):
        raise AIError(tr("Configure voice models first.", "請先設定語音模型。"))
    endpoint_url(config["url"], mode, config["key"])
    print(tr("Audio stays on the Pi. The transcript is sent to the selected AI service.",
             "錄音留在 Pi。辨識文字會送到目前選定的 AI 服務。"))
    text = listen_mandarin()
    if not text:
        return

    with tempfile.TemporaryDirectory(prefix="aion-voice-") as work:
        reply = ask(mode, config, text, instructions="請用自然的繁體中文回答，最多三句短句。")
        print(reply)
        print(tr("Generating AI speech…", "正在合成 AI 語音…"), flush=True)
        speech = post(mode, config, "/audio/speech", {
            "model": config["speech_model"], "voice": config["voice"],
            "input": reply[:1000], "response_format": "wav",
        }, limit=MAX_SPEECH)
        if speech[:4] != b"RIFF" or speech[8:12] != b"WAVE":
            raise AIError(tr("The service did not return WAV audio.", "服務未傳回 WAV 音訊。"))
        reply_path = Path(work) / "reply.wav"
        reply_path.write_bytes(speech)
        backend = os.environ.get("AION_AUDIO_BACKEND", "alsa")
        backend = backend if backend in ("alsa", "pulse") else "alsa"
        try:
            subprocess.run(
                ["mpv", "--no-config", "--no-video", "--no-terminal", f"--ao={backend}", "--", str(reply_path)],
                stdin=subprocess.DEVNULL, timeout=90, check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AIError(tr("Could not play the AI voice reply.", "無法播放 AI 語音回覆。")) from exc


PIPER_DIR = "/mnt/music/aion-piper"
PIPER_ZH_MODEL = "/mnt/music/aion-tts/zh_TW-huayan-medium.onnx"
PIPER_EN_MODEL = "/mnt/music/aion-tts/en_US-lessac-medium.onnx"


def offline_speak(text):
    """Speak one AI reply with Piper TTS on the Pi."""
    from aion_voice import set_audio_busy

    clean = terminal_text(text).strip()
    if not clean:
        return

    clean = re.sub(r"```.*?```", " ", clean, flags=re.DOTALL)
    clean = re.sub(r"[*_`#]", "", clean).strip()
    if not clean:
        return

    model = PIPER_ZH_MODEL if re.search(r"[\\u3400-\\u9fff]", clean) else PIPER_EN_MODEL
    work = tempfile.NamedTemporaryFile(prefix="aion-piper-", suffix=".wav", delete=False)
    work.close()
    reply_path = Path(work.name)

    set_audio_busy(True)
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = PIPER_DIR
        env.setdefault("PULSE_SERVER", "unix:/run/aion-pulse/pulse/native")
        env.setdefault("PULSE_COOKIE", "/var/lib/aion-audio/.config/pulse/cookie")
        subprocess.run(
            ["python3", "-m", "piper", "--model", model, "--output_file", str(reply_path)],
            input=clean, text=True, env=env,
        )
        subprocess.run(
            ["mpv", "--no-config", "--no-video", "--no-terminal", "--ao=pulse", "--", str(reply_path)],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=90, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise AIError(tr("Could not play the Piper voice reply.", "無法播放 Piper 語音回覆。"))
    finally:
        reply_path.unlink(missing_ok=True)
        set_audio_busy(False)


def load_connection(mode):
    path = config_path(mode)
    if not path.exists():
        return {}
    saved = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(saved, dict) or not all(isinstance(saved.get(key), str) for key in ("url", "model", "key")):
        raise AIError(tr("The AI connection settings could not be read.", "無法讀取 AI 連線設定。"))
    return saved


def connection_menu(mode, title):
    while True:
        screen(title)
        options((
            (1, tr("Send a message", "傳送訊息")),
            (2, tr("Configure connection", "設定連線")),
            (3, tr("Mandarin voice interaction", "中文語音互動")),
            (4, tr("Configure voice models", "設定語音模型")),
            (0, tr("Back", "返回")),
        ))
        choice = selection()
        if choice in ("", "0"):
            return
        try:
            if choice == "2":
                configure(mode, load_connection(mode))
            elif choice in ("1", "3", "4"):
                config = load_connection(mode)
                if not config:
                    print(tr("Configure this AI connection first.", "請先設定此 AI 連線。"))
                    continue
                if choice == "3":
                    voice_turn(mode, config)
                elif choice == "4":
                    configure_voice(mode, config)
                else:
                    message = input(tr("Message (Enter to cancel): ", "訊息（按 Enter 取消）：")).strip()
                    if message:
                        print(tr("Waiting for AI…", "正在等候 AI 回覆…"), flush=True)
                        print("\n" + ask(mode, config, message))
            else:
                print(tr("Invalid selection.", "選項無效。"))
        except HTTPError as error:
            print(f"{tr('AI service returned HTTP', 'AI 服務傳回 HTTP')} {error.code}")
        except (URLError, TimeoutError):
            print(tr("Could not reach the AI service.", "無法連上 AI 服務。"))
        except AIError as error:
            print(error)
        except (OSError, ValueError):
            print(tr("The AI connection settings could not be read.", "無法讀取 AI 連線設定。"))
        except KeyboardInterrupt:
            print()
            return


def ai_menu():
    from aion_oauth import run_oauth_menu

    while True:
        local = tr("Local or home network AI", "本機或家中區網 AI")
        cloud = tr("Cloud AI", "雲端 AI")
        screen(tr("AI connections", "AI 連線"))
        options((
            (1, local), (2, cloud), (3, "Google Gemini OAuth"),
            (4, "Continue with ChatGPT"),
            (5, tr("Offline Mandarin transcription", "離線中文語音辨識")),
            (0, tr("Back", "返回")),
        ))
        choice = selection()
        if choice in ("", "0"):
            return
        if choice == "1":
            connection_menu("local", local)
        elif choice == "2":
            connection_menu("cloud", cloud)
        elif choice in ("3", "4"):
            run_oauth_menu("google" if choice == "3" else "openai")
        elif choice == "5":
            try:
                listen_mandarin()
            except AIError as error:
                print(error)
            except KeyboardInterrupt:
                print()
        else:
            print(tr("Invalid selection.", "選項無效。"))


def quick_response(message):
    """Send text from the main screen using NVIDIA LM Studio first."""
    message = terminal_text(message).strip()
    if not message:
        raise AIError(tr("Enter an AI command.", "請輸入 AI 指令。"))

    lmstudio = {"url": "http://192.168.86.190:1234/v1", "model": "google/gemma-4-12b-qat", "key": ""}
    try:
        return ask("local", lmstudio, message)
    except (HTTPError, URLError, TimeoutError, OSError, AIError, TypeError, ValueError):
        pass

    for mode in ("cloud", "local"):
        try:
            config = load_connection(mode)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if config:
            return ask(mode, config, message)

    raise AIError(tr("Configure an AI connection first.", "請先設定 AI 連線。"))


def quick_prompt(message=None):
    from aion_voice import set_audio_busy

    if message is None:
        message = input(tr("AI command (Enter to cancel): ", "AI 指令（按 Enter 取消）：")).strip()
    if not message:
        return ""
    print(tr("Waiting for AI…", "正在等候 AI 回覆…"), flush=True)
    set_audio_busy(True)
    try:
        reply = quick_response(message)
        print("\n" + reply, flush=True)
        try:
            offline_speak(reply)
        except AIError as exc:
            print(str(exc), flush=True)
        return reply
    finally:
        set_audio_busy(False)
