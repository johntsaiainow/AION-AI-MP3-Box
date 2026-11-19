"""Browser sign-in for Gemini and the ChatGPT plan Responses API."""

import base64
from contextlib import contextmanager
import fcntl
from getpass import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, build_opener
from uuid import uuid4

from aion_ai import AIError, MAX_RESPONSE, NoRedirect, config_path, save_connection, terminal_text
from aion_ui import options, screen, selection, tr

PORT = 8765
CALLBACK = f"http://127.0.0.1:{PORT}/auth/callback"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/generative-language.retriever"
OPENAI_ISSUER = "https://auth.openai.com"
OPENAI_TOKEN = OPENAI_ISSUER + "/api/accounts/oauth/token"
OPENAI_API = "https://api.openai.com/v1"
OPENAI_SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


def request(url, data=None, *, encode_form=False, token="", project=""):
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if encode_form else "application/json"
        data = (urlencode(data) if encode_form else json.dumps(data)).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if project:
        headers["x-goog-user-project"] = project
    return build_opener(NoRedirect()).open(Request(url, data=data, headers=headers), timeout=45)


def request_json(*args, limit=MAX_RESPONSE, **kwargs):
    with request(*args, **kwargs) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Oversized OAuth response")
    result = json.loads(body) if body else {}
    if not isinstance(result, dict):
        raise ValueError("Invalid OAuth response")
    return result


@contextmanager
def credentials():
    path = config_path("oauth")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        book = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        yield book


def save_book(book):
    save_connection("oauth", book, announce=False)


def authorize(auth_url, parameters, state):
    class Callback(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass

        def do_GET(self):
            parts = urlsplit(self.path)
            values = parse_qs(parts.query)
            if parts.path == "/" and not parts.query:
                self.send_response(303)
                self.send_header("Location", auth_url + "?" + urlencode(parameters))
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                return
            returned = values.get("state", [])
            valid = parts.path == "/auth/callback" and len(returned) == 1 and secrets.compare_digest(returned[0], state)
            if valid:
                self.server.result = values
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(b"Return to AION to see the sign-in result." if valid else b"Invalid callback.")

    with HTTPServer(("127.0.0.1", PORT), Callback) as server:
        server.result = None
        server.timeout = 1
        print(tr("On your computer, open an SSH tunnel to the Pi:",
                 "請在電腦上開啟到 Pi 的 SSH 通道："))
        print(f"ssh -N -L 127.0.0.1:{PORT}:127.0.0.1:{PORT} root@aion.local")
        print(tr("Then open this address in a browser within five minutes:",
                 "接著在五分鐘內用瀏覽器開啟此網址："))
        print(f"http://127.0.0.1:{PORT}/", flush=True)
        deadline = time.monotonic() + 300
        while server.result is None and time.monotonic() < deadline:
            server.handle_request()
        result = server.result or {}
    if "error" in result or len(result.get("code", [])) != 1:
        raise ValueError("Authorization declined or expired")
    return result


def login_parameters():
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, state, {
        "response_type": "code", "redirect_uri": CALLBACK, "state": state,
        "code_challenge_method": "S256", "code_challenge": challenge,
    }


def save_tokens(record, token, *, openai=False):
    access = token["access_token"]
    refresh = token.get("refresh_token") or record.get("refresh_token")
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise ValueError("Provider did not grant renewable access")
    scope = token.get("scope", record.get("scope", ""))
    if openai and not {"resource.invoke", "chatgpt.tokens.use.direct"} <= set(scope.split()):
        raise ValueError("ChatGPT plan usage permission not granted")
    return {**record, "access_token": access, "refresh_token": refresh,
            "expires": time.time() + int(token["expires_in"]), "scope": scope}


def google_login(book):
    saved = book.get("google", {})
    client = input(tr("Google OAuth Desktop client ID: ", "Google OAuth 桌面用戶端 ID：")).strip() or saved.get("client_id", "")
    secret = getpass(tr("Google OAuth Desktop client secret: ", "Google OAuth 桌面用戶端密鑰：")).strip()
    if not secret and client == saved.get("client_id"):
        secret = saved.get("client_secret", "")
    project = input(tr("Google Cloud project ID: ", "Google Cloud 專案 ID：")).strip() or saved.get("project", "")
    model = input(tr("Gemini model: ", "Gemini 模型：")).strip() or saved.get("model", "")
    if not all((client, secret, project, model)) or not all(char.isascii() and (char.isalnum() or char == "-") for char in project):
        raise ValueError("Google OAuth settings are incomplete")
    verifier, state, params = login_parameters()
    reply = authorize(GOOGLE_AUTH, {**params, "client_id": client, "scope": GOOGLE_SCOPE,
                                   "access_type": "offline", "prompt": "consent"}, state)
    token = request_json(GOOGLE_TOKEN, {
        "grant_type": "authorization_code", "client_id": client,
        "client_secret": secret, "code": reply["code"][0],
        "redirect_uri": CALLBACK, "code_verifier": verifier,
    }, encode_form=True)
    book["google"] = save_tokens({"client_id": client, "client_secret": secret,
                                 "project": project, "model": model}, token)
    save_book(book)


def oidc_claims(id_token, client, nonce):
    def b64(value):
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def der(tag, value):
        length = len(value)
        prefix = bytes((length,)) if length < 128 else length.to_bytes((length.bit_length() + 7) // 8, "big")
        return bytes((tag,)) + (b"" if length < 128 else bytes((128 | len(prefix),))) + prefix + value

    def integer(value):
        raw = b64(value).lstrip(b"\x00")
        return der(2, (b"\x00" if raw[0] & 128 else b"") + raw)

    header_part, claims_part, signature = id_token.split(".")
    header = json.loads(b64(header_part))
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("Unexpected ID token signing algorithm")
    keys = request_json(OPENAI_ISSUER + "/.well-known/jwks.json")["keys"]
    key = next((key for key in keys if key.get("kid") == header["kid"] and key.get("kty") == "RSA"), None)
    if not key:
        raise ValueError("Unknown ID token key")
    rsa_key = der(48, integer(key["n"]) + integer(key["e"]))
    # SubjectPublicKeyInfo with the rsaEncryption algorithm identifier.
    public_key = der(48, bytes.fromhex("300d06092a864886f70d0101010500") + der(3, b"\x00" + rsa_key))
    with tempfile.TemporaryDirectory(prefix="aion-oidc-") as temporary:
        public = Path(temporary) / "public.der"
        signature_file = Path(temporary) / "signature"
        public.write_bytes(public_key)
        signature_file.write_bytes(b64(signature))
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-keyform", "DER", "-verify", str(public),
             "-signature", str(signature_file)],
            input=f"{header_part}.{claims_part}".encode(), timeout=5, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    claims = json.loads(b64(claims_part))
    audience = claims.get("aud")
    if isinstance(audience, str):
        audience = [audience]
    if (
        claims.get("iss") != OPENAI_ISSUER or not isinstance(audience, list)
        or client not in audience or (len(audience) > 1 and claims.get("azp") != client)
        or int(claims.get("exp", 0)) <= time.time() or claims.get("nonce") != nonce
        or not isinstance(claims.get("sub"), str) or not claims["sub"]
    ):
        raise ValueError("Invalid ID token claims")
    return claims


def openai_login(book, saved):
    host = book.get("openai_host")
    if not host:
        host = uuid4().urn
        book["openai_host"] = host
        save_book(book)
    verifier, state, params = login_parameters()
    nonce = secrets.token_urlsafe(32)
    params.update({
        "client_id": saved.get("client_id", "dynamic_agent_client"), "ext_agent_host_id": host,
        "nonce": nonce, "scope": OPENAI_SCOPE, "resource": OPENAI_API,
    })
    if not saved:
        params["agent_name_hint"] = "AION AI MP3 Box"
    reply = authorize(OPENAI_ISSUER + "/api/accounts/authorize", params, state)
    client = reply.get("client_id", [saved.get("client_id", "")])[0]
    if not client or client == "dynamic_agent_client" or (saved and client != saved["client_id"]):
        raise ValueError("Registration does not match the requested account")
    token = request_json(OPENAI_TOKEN, {
        "grant_type": "authorization_code", "client_id": client, "code": reply["code"][0],
        "redirect_uri": CALLBACK, "code_verifier": verifier, "resource": OPENAI_API,
    }, encode_form=True)
    claims = oidc_claims(token["id_token"], client, nonce)
    accounts = book.setdefault("openai", {})
    previous = accounts.get(client, saved)
    if previous and claims["sub"] != previous["subject"]:
        raise ValueError("The signed-in account changed")
    accounts[client] = save_tokens({
        "client_id": client, "subject": claims["sub"], "email": claims.get("email", ""),
    }, token, openai=True)
    save_book(book)
    return accounts[client]


def access_token(book, record, provider):
    if record.get("access_token") and record.get("expires", 0) > time.time() + 60:
        return record["access_token"]
    arguments = {"grant_type": "refresh_token", "client_id": record["client_id"],
                 "refresh_token": record["refresh_token"]}
    if provider == "google":
        url = GOOGLE_TOKEN
        arguments["client_secret"] = record["client_secret"]
    else:
        url = OPENAI_TOKEN
        arguments["resource"] = OPENAI_API
    record.update(save_tokens(record, request_json(url, arguments, encode_form=True), openai=provider == "openai"))
    save_book(book)
    return record["access_token"]


def google_chat(record, token, message):
    model = quote(record["model"].removeprefix("models/"), safe="")
    answer = request_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"contents": [{"role": "user", "parts": [{"text": message}]}]},
        token=token, project=record["project"],
    )
    return "".join(part.get("text", "") for part in answer["candidates"][0]["content"]["parts"])


def openai_chat(token, model, message):
    fragments = []
    size = 0
    with request(OPENAI_API + "/responses", {
        "model": model, "input": [{"role": "user", "content": message}],
        "store": False, "stream": True,
    }, token=token) as stream:
        while True:
            line = stream.readline(MAX_RESPONSE + 1)
            size += len(line)
            if not line or size > MAX_RESPONSE:
                break
            if not line.startswith(b"data:"):
                continue
            message = json.loads(line[5:])
            event = message.get("type")
            if event == "response.output_text.delta":
                fragments.append(message["delta"])
            elif event == "response.completed":
                return "".join(fragments)
            elif event in ("response.failed", "response.incomplete", "error"):
                break
    raise ValueError("Responses stream did not finish")


def choose(records):
    options((index, terminal_text(label)) for index, label in enumerate(records, 1))
    selected = selection()
    return int(selected) - 1 if selected.isascii() and selected.isdecimal() and len(selected) < 5 and 1 <= int(selected) <= len(records) else None


def sign_out(book, record, provider):
    if not record.get("refresh_token"):
        return
    token = record["refresh_token"]
    url = "https://oauth2.googleapis.com/revoke"
    arguments = {"token": token}
    if provider == "openai":
        url = OPENAI_ISSUER + "/api/accounts/oauth/revoke"
        arguments.update(token_type_hint="refresh_token", client_id=record["client_id"])
    try:
        request_json(url, arguments, encode_form=True)
    except (OSError, ValueError):
        print(tr("Remote revocation could not be confirmed.", "無法確認遠端權杖已撤銷。"))
    for field in ("access_token", "refresh_token", "expires", "scope"):
        record.pop(field, None)
    save_book(book)
    print(tr("Signed out on this device.", "已在此設備登出。"))


def oauth_menu(provider):
    title = "Google Gemini OAuth" if provider == "google" else "Continue with ChatGPT"
    with credentials() as book:
        accounts = list(book.get("openai", {}).values())
        record = book.get("google") if provider == "google" else None
        screen(title)
        options((
            (1, tr("Sign in", "登入")),
            (2, tr("Send a message", "傳送訊息")),
            (3, tr("Sign out", "登出")),
            (0, tr("Back", "返回")),
        ))
        action = selection()
        if action not in ("1", "2", "3"):
            return
        if provider == "openai" and accounts:
            if action == "1":
                accounts = [{}, *accounts]
            labels = [f"{account['email'] or 'ChatGPT'} · {account['client_id'][-8:]}"
                      if account else tr("Add another account", "新增其他帳戶") for account in accounts]
            index = choose(labels)
            if index is None:
                return
            record = accounts[index]
        if action == "1":
            if provider == "google":
                google_login(book)
            else:
                openai_login(book, record or {})
            print(tr("OAuth sign-in complete.", "OAuth 登入完成。"))
            return
        if not record or not record.get("refresh_token"):
            raise AIError(tr("Sign in first.", "請先登入。"))
        if action == "3":
            sign_out(book, record, provider)
            return
        token = access_token(book, record, provider)
        if provider == "openai":
            models = [model for model in request_json(OPENAI_API + "/models", token=token)["models"]
                      if model.get("visibility") == "list"]
            index = choose([model["display_name"] for model in models])
            if index is None:
                return
        text = input(tr("Message (Enter to cancel): ", "訊息（按 Enter 取消）：")).strip()
        if text:
            reply = google_chat(record, token, text) if provider == "google" else openai_chat(token, models[index]["slug"], text)
            print(terminal_text(reply) or tr("The service returned no text reply.", "服務未傳回文字回覆。"))


def run_oauth_menu(provider):
    try:
        oauth_menu(provider)
    except HTTPError as error:
        print(f"{tr('AI service returned HTTP', 'AI 服務傳回 HTTP')} {error.code}")
    except AIError as error:
        print(error)
    except (KeyError, IndexError, OSError, TypeError, ValueError, subprocess.SubprocessError):
        print(tr("OAuth request failed. Check your settings or sign in again.",
                 "OAuth 請求失敗。請檢查設定或重新登入。"))
    except KeyboardInterrupt:
        print()


def openai_quick_response(message):
    """Send a text turn through the currently active ChatGPT OAuth account."""
    message = terminal_text(message).strip()
    if not message:
        raise AIError(tr("Enter an AI command.", "請輸入 AI 指令。"))

    with credentials() as book:
        accounts = list(book.get("openai", {}).values())
        if not accounts:
            raise AIError(tr("Sign in with ChatGPT first.", "請先登入 ChatGPT。"))

        record = next((account for account in accounts if account.get("active")), accounts[0])
        token = access_token(book, record, "openai")

    models = [model for model in request_json(OPENAI_API + "/models", limit=1024 * 1024, token=token)["models"]
              if model.get("visibility") == "list"]
    if not models:
        raise ValueError("No OpenAI models are available")

    preferred = record.get("model")
    model = next((item for item in models if item.get("slug") == preferred), models[0])
    reply = openai_chat(token, model["slug"], message)
    return terminal_text(reply)
