"""WhatsApp Business Platform - official Cloud API only (graph.facebook.com).

No Baileys / whatsapp-web.js: unofficial clients violate Meta ToS and get the number banned.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from ..core.models import Incoming, Out

BTN_TITLE = 20      # reply button title limit
ROW_TITLE = 24      # list row title limit
ROW_DESC = 72
BODY_MAX = 1024     # interactive body limit
WINDOW = timedelta(hours=24)  # customer service window


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def window_open(last_in: Optional[str], now: Optional[datetime] = None) -> bool:
    if not last_in:
        return False
    now = now or datetime.now(timezone.utc)
    return now - datetime.fromisoformat(last_in) < WINDOW


def render(out: Out, to: str, use_template: bool = False) -> dict:
    """Out -> Cloud API /messages payload."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
    if use_template and out.template:
        tpl = out.template
        comps = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in tpl.params]}]
        for i, b in enumerate(out.buttons[:3]):
            comps.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                          "parameters": [{"type": "payload", "payload": b.id}]})
        return {**base, "type": "template",
                "template": {"name": tpl.name, "language": {"code": tpl.lang}, "components": comps}}
    if not out.buttons:
        return {**base, "type": "text", "text": {"preview_url": False, "body": out.text}}
    if len(out.buttons) <= 3 and all(len(b.title) <= BTN_TITLE for b in out.buttons):
        return {**base, "type": "interactive", "interactive": {
            "type": "button",
            "body": {"text": _cut(out.text, BODY_MAX)},
            "action": {"buttons": [{"type": "reply", "reply": {"id": b.id, "title": b.title}}
                                   for b in out.buttons]}}}
    rows = []
    for b in out.buttons[:10]:
        row = {"id": b.id, "title": _cut(b.title, ROW_TITLE)}
        if len(b.title) > ROW_TITLE:
            row["description"] = _cut(b.title, ROW_DESC)
        rows.append(row)
    return {**base, "type": "interactive", "interactive": {
        "type": "list",
        "body": {"text": _cut(out.text, BODY_MAX)},
        "action": {"button": _cut(out.list_title or "Choose", BTN_TITLE),
                   "sections": [{"title": "Options", "rows": rows}]}}}


class WhatsAppAdapter:
    channel = "whatsapp"

    def __init__(self, token: str, phone_number_id: str, app_secret: str = "",
                 api_version: str = "v23.0", client: Optional[httpx.AsyncClient] = None,
                 clock=lambda: datetime.now(timezone.utc)):
        self.token = token
        self.phone_number_id = phone_number_id
        self.app_secret = app_secret
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.client = client or httpx.AsyncClient(timeout=15)
        self.clock = clock

    # ---- inbound --------------------------------------------------
    def verify_signature(self, raw: bytes, headers: dict) -> bool:
        if not self.app_secret:
            return True  # not configured (local dev); set WA_APP_SECRET in production
        sig = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(self.app_secret.encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def parse(self, body: dict) -> list[Incoming]:
        out = []
        for entry in body.get("entry", []):
            for ch in entry.get("changes", []):
                value = ch.get("value", {})
                names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
                for m in value.get("messages", []):
                    frm = m.get("from")
                    typ = m.get("type")
                    inc = Incoming(self.channel, frm, name=names.get(frm))
                    if typ == "text":
                        inc.text = m["text"]["body"]
                    elif typ == "interactive":
                        it = m["interactive"]
                        inc.payload = (it.get("button_reply") or it.get("list_reply") or {}).get("id")
                    elif typ == "button":  # quick reply on a template
                        inc.payload = m["button"].get("payload")
                    else:
                        inc.text = ""  # image, audio, ... -> "use the buttons"
                    out.append(inc)
        return out

    # ---- outbound -------------------------------------------------
    async def send(self, user_id: str, outs: list[Out], last_in: Optional[str] = None) -> list[dict]:
        sent = []
        open_ = window_open(last_in, self.clock())
        for o in outs:
            payload = render(o, user_id, use_template=not open_)
            # outside the 24h window Meta accepts only approved templates
            if open_ or payload["type"] == "template":
                r = await self.client.post(self.url, json=payload,
                                           headers={"Authorization": f"Bearer {self.token}"})
                r.raise_for_status()
                sent.append(payload)
        return sent
