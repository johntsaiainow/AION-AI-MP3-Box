#!/usr/bin/env python3
"""Read SMS from a paired phone through an isolated BlueZ MAP session."""

import asyncio
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus

from aion_ui import tr, use_saved_language


OBEX = "org.bluez.obex"
PROPERTIES = "org.freedesktop.DBus.Properties"
SMS_TYPES = {"sms-gsm", "sms-cdma"}


def plain_text(value):
    return "".join(char for char in str(value) if char.isprintable() or char in "\n\t")


def label(value):
    return " ".join(plain_text(value).split())


def parse_vcard(vcard_text):
    sender_name = ""
    sender_tel = ""
    fn = re.search(r"^FN[;:](.*)$", vcard_text, re.MULTILINE | re.IGNORECASE)
    n = re.search(r"^N[;:](.*)$", vcard_text, re.MULTILINE | re.IGNORECASE)
    tel = re.search(r"^TEL[^:]*:(.*)$", vcard_text, re.MULTILINE | re.IGNORECASE)
    if fn and fn.group(1).strip():
        sender_name = fn.group(1).strip()
    elif n and n.group(1).strip():
        sender_name = " ".join(part for part in n.group(1).replace(";", " ").split() if part)
    if tel and tel.group(1).strip():
        sender_tel = tel.group(1).strip()
    return sender_name, sender_tel


def extract_mime_text(body):
    if not re.match(r"(?:MIME-Version|Content-Type):", body, re.IGNORECASE):
        return body
    try:
        import email
        from email import policy
        msg = email.message_from_string(body, policy=policy.default)
        part = msg.get_body(preferencelist=("plain",))
        if part:
            return part.get_content().strip()
    except Exception:
        pass
    if "Content-Type:" in body or "MIME-Version:" in body:
        parts = re.split(r"\r?\n\r?\n", body, maxsplit=1)
        if len(parts) > 1:
            body = parts[1]
            body = re.sub(r"--[A-Za-z0-9_-]+(--)?\s*$", "", body).strip()
    return body.strip()


def parse_bmsg(content):
    sender_name = ""
    sender_tel = ""
    vcard_match = re.search(r"BEGIN:VCARD\s*(.*?)\s*END:VCARD", content, re.DOTALL | re.IGNORECASE)
    if vcard_match:
        sender_name, sender_tel = parse_vcard(vcard_match.group(1))

    msg_match = re.search(
        r"^BEGIN:MSG[ \t]*\n(.*?)^END:MSG[ \t]*$",
        content.replace("\r\n", "\n"), re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    if not msg_match:
        raise ValueError(tr("The downloaded message has no readable SMS body.", "下載的簡訊缺少可讀正文。"))
    body = extract_mime_text(re.sub(r"(?m)^/END:MSG", "END:MSG", msg_match.group(1)))
    return sender_name, sender_tel, plain_text(body).strip()


async def call(bus, destination, path, interface, member, signature="", body=None, *, timeout=20):
    reply = await asyncio.wait_for(bus.call(Message(
        destination=destination, path=path, interface=interface,
        member=member, signature=signature, body=body or [],
    )), timeout)
    if reply.message_type == MessageType.ERROR:
        message = tr("Could not read phone SMS. Check the phone's Bluetooth message access permission.",
                     "無法讀取手機簡訊。請檢查手機的藍牙簡訊存取權限。")
        raise ValueError(f"{message} ({member}: {reply.error_name})")
    return reply.body


async def read_message(bus, object_path, directory):
    target = directory / "message.bmsg"
    statuses = asyncio.Queue()

    def transfer_changed(event):
        if (event.message_type == MessageType.SIGNAL and event.interface == PROPERTIES
                and event.member == "PropertiesChanged" and event.body[0] == OBEX + ".Transfer1"):
            status = event.body[1].get("Status")
            if status and status.value in ("complete", "error"):
                statuses.put_nowait((event.path, status.value))

    # BlueZ removes the transfer object immediately after its final signal.
    bus.add_message_handler(transfer_changed)
    try:
        reply_body = await call(bus, OBEX, object_path, OBEX + ".Message1",
                                "Get", "sb", [str(target), False])
        transfer_path = reply_body[0]
        init_props = reply_body[1] if len(reply_body) > 1 and isinstance(reply_body[1], dict) else {}
        status = init_props.get("Status").value if "Status" in init_props else None

        if status != "complete":
            async with asyncio.timeout(20):
                while True:
                    path, status = await statuses.get()
                    if path == transfer_path:
                        break

        if status == "complete" and target.is_file():
            with target.open(encoding="utf-8", errors="replace") as message:
                content = message.read(65537)
            if len(content) > 65536:
                raise ValueError(tr("Message is too large.", "簡訊內容過長。"))
            return parse_bmsg(content)

        raise ValueError(tr("Message download failed.", "下載簡訊失敗。"))
    finally:
        bus.remove_message_handler(transfer_changed)
        target.unlink(missing_ok=True)


async def browse_inbox(bus, session_path, directory):
    interface = OBEX + ".MessageAccess1"
    for folder in ("telecom", "msg", "inbox"):
        await call(bus, OBEX, session_path, interface, "SetFolder", "s", [folder])
    messages, = await call(bus, OBEX, session_path, interface, "ListMessages", "sa{sv}",
                           ["", {"MaxCount": Variant("q", 30)}])

    # MAP's FilterMessageType bitmask excludes the specified types.
    rows = [
        (path, {key: value.value for key, value in details.items()})
        for path, details in messages.items()
        if "Type" in details and details["Type"].value.lower() in SMS_TYPES
    ][:30]
    if not rows:
        if messages:
            print(tr("The messages returned by the phone include no SMS.", "手機回傳的郵件中沒有 SMS 簡訊。"))
        else:
            print(tr("The phone returned an empty inbox.", "手機回傳的收件匣是空的。"))
        return

    while True:
        print(tr("\nPhone SMS", "\n手機簡訊"))
        for index, (_, details) in enumerate(rows, 1):
            sender = label(details.get("Sender") or details.get("SenderAddress") or details.get("RecipientAddress") or "")
            timestamp = label(details.get("Timestamp", ""))
            subject = label(details.get("Subject", ""))
            sender_disp = sender if sender else tr("Unknown number", "未知號碼")
            print(f"  [{index}]  {sender_disp}  {timestamp}")
            if subject:
                preview = subject[:36] + ("..." if len(subject) > 36 else "")
                print(f"       {preview}")

        choice = input(tr("\nMessage number (Enter to return): ", "\n簡訊編號（按 Enter 返回）：")).strip()
        if not choice:
            return
        if not choice.isascii() or not choice.isdecimal() or len(choice) > 2 or not 1 <= int(choice) <= len(rows):
            print(tr("Invalid selection.", "選項無效。"))
            continue
        print()
        msg_obj_path, details = rows[int(choice) - 1]
        try:
            sender_name, sender_tel, body = "", "", ""
            try:
                sender_name, sender_tel, body = await read_message(bus, msg_obj_path, directory)
            except (OSError, ValueError) as exc:
                body = plain_text(details.get("Subject", ""))
                if not body:
                    raise
                print(tr("Notice: Unable to download full message ({err}), showing preview from listing:\n",
                         "提示：無法下載完整簡訊（{err}），顯示預覽內容：\n").format(
                             err=plain_text(exc) or tr("request timed out", "要求逾時")))

            sender_tel = label(sender_tel or details.get("SenderAddress") or details.get("RecipientAddress") or "")
            sender_name = label(sender_name or details.get("Sender") or "")
            timestamp = label(details.get("Timestamp", ""))

            if sender_name and sender_tel:
                sender_str = f"{sender_name} ({sender_tel})"
            elif sender_tel:
                sender_str = sender_tel
            elif sender_name:
                sender_str = sender_name
            else:
                sender_str = tr("Unknown number", "未知號碼")

            print(f"{tr('Sender', '寄件人')}: {sender_str}")
            if timestamp:
                print(f"{tr('Time', '時間')}: {timestamp}")
            print(f"\n{body or tr('(No text content)', '（無文字內容）')}")

        except (OSError, ValueError) as exc:
            print(tr("Failed to read SMS: {err}", "無法讀取簡訊：{err}").format(
                err=plain_text(exc) or tr("request timed out", "要求逾時")))
        except Exception as exc:
            line = traceback.extract_tb(exc.__traceback__)[-1].lineno
            print(tr("SMS viewer error ({kind}, line {line}).",
                     "簡訊檢視程式發生錯誤（{kind}，第 {line} 行）。").format(
                         kind=type(exc).__name__, line=line))

        input(tr("\nPress Enter to return to the inbox.", "\n按 Enter 返回收件匣。"))
        if sys.stdout.isatty():
            print("\033[2J\033[H", end="", flush=True)


async def bus_call(bus, member, signature, body):
    interface = "org.freedesktop.DBus"
    return await call(bus, interface, "/org/freedesktop/DBus", interface, member, signature, body, timeout=5)


async def connect_client(bus, daemon):
    async with asyncio.timeout(5):
        while daemon.poll() is None:
            ready, = await bus_call(bus, "NameHasOwner", "s", [OBEX])
            if ready:
                return
            await asyncio.sleep(0.1)
    raise ValueError(tr("BlueZ OBEX did not start.", "BlueZ OBEX 未能啟動。"))


async def main(address):
    use_saved_language()
    print(tr("Allow message access on your phone if prompted.", "若手機顯示提示，請允許存取簡訊。"), flush=True)
    with tempfile.TemporaryDirectory(prefix="aion-sms-", dir="/run") as work:
        directory = Path(work)
        # BlueZ requires a service plugin at startup. MNS handles MAP notifications.
        daemon = subprocess.Popen(
            ["@LIBEXECDIR@/bluetooth/obexd", "--nodetach", "--plugin=bluetooth,mns", "--root", work],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            bus = await MessageBus().connect()
            try:
                await connect_client(bus, daemon)
                await bus_call(bus, "AddMatch", "s", [
                    f"type='signal',sender='{OBEX}',interface='{PROPERTIES}',member='PropertiesChanged'",
                ])
                path, interface = "/org/bluez/obex", OBEX + ".Client1"
                session, = await call(bus, OBEX, path, interface, "CreateSession", "sa{sv}",
                                      [address, {"Target": Variant("s", "map")}], timeout=40)
                try:
                    await browse_inbox(bus, session, directory)
                finally:
                    try:
                        await call(bus, OBEX, path, interface, "RemoveSession", "o", [session], timeout=5)
                    except (TimeoutError, ValueError):
                        pass
            finally:
                bus.disconnect()
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1]))
    except (KeyboardInterrupt, EOFError):
        pass
    except TimeoutError:
        print(tr("The Bluetooth message request timed out.", "藍牙簡訊要求逾時。"), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError) as error:
        print(plain_text(error), file=sys.stderr)
        sys.exit(1)
