"""Settings come only from environment variables (.env). Nothing secret lives in the code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", str(ROOT / "data" / "booking.db")))
    salon_file: str = field(default_factory=lambda: os.getenv("SALON_FILE", str(ROOT / "app" / "salon.json")))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Europe/Berlin"))
    # Admins: "<channel>:<user id>", e.g. "whatsapp:4915112345678,viber:abc==,emulator:admin"
    admins: list[str] = field(default_factory=lambda: _list("ADMIN_IDS"))

    # WhatsApp Cloud API (official, graph.facebook.com)
    wa_token: str = field(default_factory=lambda: os.getenv("WA_ACCESS_TOKEN", ""))
    wa_phone_number_id: str = field(default_factory=lambda: os.getenv("WA_PHONE_NUMBER_ID", ""))
    wa_verify_token: str = field(default_factory=lambda: os.getenv("WA_VERIFY_TOKEN", ""))
    wa_app_secret: str = field(default_factory=lambda: os.getenv("WA_APP_SECRET", ""))
    wa_api_version: str = field(default_factory=lambda: os.getenv("WA_API_VERSION", "v23.0"))
    wa_reminder_template: str = field(default_factory=lambda: os.getenv("WA_REMINDER_TEMPLATE", "appointment_reminder"))

    # Viber Bot API (chatapi.viber.com)
    viber_token: str = field(default_factory=lambda: os.getenv("VIBER_AUTH_TOKEN", ""))
    viber_bot_name: str = field(default_factory=lambda: os.getenv("VIBER_BOT_NAME", "Salon Bot"))

    # Demo / emulator
    demo_mode: bool = field(default_factory=lambda: os.getenv("DEMO_MODE", "1") == "1")
    reminder_interval_s: int = field(default_factory=lambda: int(os.getenv("REMINDER_INTERVAL_S", "60")))

    # Optional export
    sheets_exporter: str = field(default_factory=lambda: os.getenv("SHEETS_EXPORTER", "none"))  # none|csv|google
    google_sheet_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", ""))
    google_credentials_file: str = field(default_factory=lambda: os.getenv("GOOGLE_CREDENTIALS_FILE", ""))

    def is_admin(self, channel: str, user_id: str) -> bool:
        return f"{channel}:{user_id}" in self.admins
