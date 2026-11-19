"""Adapter contract: every messenger turns its webhook into Incoming and Out into its own API calls."""
from __future__ import annotations

from typing import Optional, Protocol

from ..core.models import Incoming, Out


class Adapter(Protocol):
    channel: str

    def verify_signature(self, raw: bytes, headers: dict) -> bool: ...

    def parse(self, body: dict) -> list[Incoming]: ...

    async def send(self, user_id: str, outs: list[Out], last_in: Optional[str] = None) -> list[dict]: ...
