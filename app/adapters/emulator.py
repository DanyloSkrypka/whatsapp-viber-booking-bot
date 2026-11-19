"""Local emulator: keeps the exact WhatsApp Cloud API payloads in memory for the demo page."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ..core.models import Incoming, Out
from . import whatsapp


class EmulatorAdapter:
    channel = "emulator"

    def __init__(self):
        self.outbox: dict[str, list[dict]] = defaultdict(list)

    def verify_signature(self, raw: bytes, headers: dict) -> bool:
        return True

    def parse(self, body: dict) -> list[Incoming]:
        return [Incoming(self.channel, body["user"], text=body.get("text"), payload=body.get("payload"))]

    async def send(self, user_id: str, outs: list[Out], last_in: Optional[str] = None) -> list[dict]:
        sent = []
        for o in outs:
            p = whatsapp.render(o, user_id, use_template=False)
            if o.template:
                p["_template"] = o.template.name  # shown as a small badge on the page
            self.outbox[user_id].append(p)
            sent.append(p)
        return sent

    def drain(self, user_id: str) -> list[dict]:
        msgs = self.outbox.pop(user_id, [])
        return msgs
