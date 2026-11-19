"""Viber Bot API (chatapi.viber.com). Needs a commercial chatbot account (monthly fee, see README)."""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional

import httpx

from ..core.models import Incoming, Out

API = "https://chatapi.viber.com/pa"
PAYLOAD_PREFIX = "#"   # keyboard buttons send "#<id>" so we can tell taps from typed text


def keyboard(out: Out) -> Optional[dict]:
    if not out.buttons:
        return None
    btns = []
    for b in out.buttons[:24]:
        btns.append({"Columns": 3 if len(out.buttons) > 3 else 6, "Rows": 1,
                     "ActionType": "reply", "ActionBody": PAYLOAD_PREFIX + b.id,
                     "Text": b.title, "TextSize": "regular", "BgColor": "#F2EEFF", "Silent": False})
    return {"Type": "keyboard", "DefaultHeight": False, "InputFieldState": "regular", "Buttons": btns}


def render(out: Out, receiver: Optional[str], sender_name: str) -> dict:
    msg = {"min_api_version": 7, "sender": {"name": sender_name}, "type": "text", "text": out.text[:7000]}
    if receiver:
        msg["receiver"] = receiver
    kb = keyboard(out)
    if kb:
        msg["keyboard"] = kb
    return msg


class ViberAdapter:
    channel = "viber"

    def __init__(self, token: str, bot_name: str = "Salon Bot", client: Optional[httpx.AsyncClient] = None):
        self.token = token
        self.bot_name = bot_name
        self.client = client or httpx.AsyncClient(timeout=15)

    def verify_signature(self, raw: bytes, headers: dict) -> bool:
        sig = headers.get("x-viber-content-signature", "")
        expected = hmac.new(self.token.encode(), raw, hashlib.sha256).hexdigest()
        return bool(self.token) and hmac.compare_digest(sig, expected)

    def parse(self, body: dict) -> list[Incoming]:
        ev = body.get("event")
        if ev == "message":
            sender = body.get("sender", {})
            m = body.get("message", {})
            inc = Incoming(self.channel, sender.get("id"), name=sender.get("name"))
            text = m.get("text") or ""
            if m.get("type") == "text" and text.startswith(PAYLOAD_PREFIX):
                inc.payload = text[len(PAYLOAD_PREFIX):]
            else:
                inc.text = text if m.get("type") == "text" else ""
            return [inc]
        if ev == "conversation_started":
            user = body.get("user", {})
            return [Incoming(self.channel, user.get("id"), text="start", name=user.get("name"))]
        return []  # webhook, delivered, seen, subscribed, unsubscribed, failed

    def welcome(self, outs: list[Out]) -> dict:
        """conversation_started may be answered with ONE message in the HTTP response."""
        text = "\n\n".join(o.text for o in outs)
        last = outs[-1] if outs else Out("")
        return render(Out(text, last.buttons, last.list_title), None, self.bot_name)

    async def send(self, user_id: str, outs: list[Out], last_in: Optional[str] = None) -> list[dict]:
        sent = []
        for o in outs:
            payload = render(o, user_id, self.bot_name)
            r = await self.client.post(f"{API}/send_message", json=payload,
                                       headers={"X-Viber-Auth-Token": self.token})
            r.raise_for_status()
            data = r.json()
            if data.get("status") != 0:
                raise RuntimeError(f"Viber error {data.get('status')}: {data.get('status_message')}")
            sent.append(payload)
        return sent

    async def set_webhook(self, url: str) -> dict:
        r = await self.client.post(f"{API}/set_webhook", headers={"X-Viber-Auth-Token": self.token},
                                   json={"url": url, "event_types": ["delivered", "seen", "failed",
                                                                     "subscribed", "unsubscribed",
                                                                     "conversation_started"],
                                         "send_name": True})
        return r.json()
