"""Messenger-neutral message model. Adapters translate it to WhatsApp / Viber / emulator payloads."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Button:
    id: str      # payload sent back when pressed
    title: str   # visible label


@dataclass
class Template:
    """Pre-approved template (needed by WhatsApp outside the 24h customer-service window)."""
    name: str
    lang: str
    params: list[str]


@dataclass
class Out:
    text: str
    buttons: list[Button] = field(default_factory=list)
    list_title: Optional[str] = None      # if set and many options -> render as a list menu
    template: Optional[Template] = None   # for business-initiated messages (reminders)


@dataclass
class Incoming:
    channel: str            # whatsapp | viber | emulator
    user_id: str
    text: Optional[str] = None
    payload: Optional[str] = None   # button id
    name: Optional[str] = None

    @property
    def user_key(self) -> str:
        return f"{self.channel}:{self.user_id}"
