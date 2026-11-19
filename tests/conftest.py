import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# tests never touch the real database
os.environ["DB_PATH"] = ":memory:"
os.environ.setdefault("DEMO_MODE", "1")

from app.config import Settings  # noqa: E402
from app.core.db import DB  # noqa: E402
from app.core.engine import Engine, load_salon  # noqa: E402
from app.core.models import Incoming  # noqa: E402
from app.main import Clock, create_app  # noqa: E402

# Wednesday 18.11.2026, 09:00 in Berlin
START = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def clock():
    c = Clock()
    c.fixed = START
    return c


@pytest.fixture
def engine(clock):
    salon = load_salon(str(ROOT / "app" / "salon.json"))
    return Engine(DB(":memory:"), salon, "Europe/Berlin", clock, admins=["emulator:admin"])


class Chat:
    """Tiny helper: talk to the engine like a user."""

    def __init__(self, engine, user="u1", channel="emulator"):
        self.e = engine
        self.user = user
        self.channel = channel
        self.last = []

    def say(self, text):
        self.last = self.e.handle(Incoming(self.channel, self.user, text=text))
        return self.last

    def tap(self, payload):
        self.last = self.e.handle(Incoming(self.channel, self.user, payload=payload))
        return self.last

    def ids(self):
        return [b.id for o in self.last for b in o.buttons]

    def text(self):
        return "\n".join(o.text for o in self.last)


@pytest.fixture
def chat(engine):
    return Chat(engine)


class Recorder:
    """httpx MockTransport that records every outgoing API call."""

    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"messages": [{"id": "wamid.TEST"}]}

    def __call__(self, request: httpx.Request):
        self.calls.append({"url": str(request.url), "headers": dict(request.headers),
                           "json": json.loads(request.content or b"{}")})
        return httpx.Response(200, json=self.response)

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self))


@pytest.fixture
def api(clock):
    """FastAPI app with mocked WhatsApp + Viber HTTP."""
    wa = Recorder()
    vb = Recorder({"status": 0, "status_message": "ok", "message_token": 1})
    settings = Settings()
    settings.db_path = ":memory:"
    settings.wa_token = "WA_TEST_TOKEN"
    settings.wa_phone_number_id = "123456"
    settings.wa_verify_token = "verify-me"
    settings.wa_app_secret = "app-secret"
    settings.viber_token = "viber-token"
    settings.admins = ["whatsapp:491700000001"]
    app = create_app(settings, wa_client=wa.client(), viber_client=vb.client(), clock=clock, run_scheduler=False)
    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        yield tc, app, wa, vb
