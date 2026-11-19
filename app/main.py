"""FastAPI app: webhooks for WhatsApp Cloud API and Viber, local emulator API, reminder loop.

Run:  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .adapters.emulator import EmulatorAdapter
from .adapters.viber import ViberAdapter
from .adapters.whatsapp import WhatsAppAdapter
from .config import ROOT, Settings
from .core.db import DB
from .core.engine import Engine, load_salon
from .core.models import Incoming
from .export import make_exporter

log = logging.getLogger("booking-bot")


class Clock:
    """Real UTC time plus an offset the demo page can move forward ("time travel" for reminders)."""

    def __init__(self):
        self.offset = timedelta()
        self.fixed: Optional[datetime] = None

    def __call__(self) -> datetime:
        base = self.fixed or datetime.now(timezone.utc)
        return base + self.offset


def create_app(settings: Optional[Settings] = None, wa_client=None, viber_client=None,
               clock: Optional[Clock] = None, run_scheduler: bool = True) -> FastAPI:
    settings = settings or Settings()
    clock = clock or Clock()
    admins = list(settings.admins)
    if settings.demo_mode and "emulator:admin" not in admins:
        admins.append("emulator:admin")
    db = DB(settings.db_path)
    exporter = make_exporter(settings.sheets_exporter, path=str(ROOT / "data" / "bookings.csv"),
                             sheet_id=settings.google_sheet_id,
                             credentials_file=settings.google_credentials_file)
    engine = Engine(db, load_salon(settings.salon_file), settings.timezone, clock, admins, exporter)
    adapters = {
        "whatsapp": WhatsAppAdapter(settings.wa_token, settings.wa_phone_number_id, settings.wa_app_secret,
                                    settings.wa_api_version, client=wa_client, clock=clock),
        "viber": ViberAdapter(settings.viber_token, settings.viber_bot_name, client=viber_client),
        "emulator": EmulatorAdapter(),
    }

    async def deliver(user_key: str, outs) -> None:
        channel, _, uid = user_key.partition(":")
        ad = adapters.get(channel)
        if not ad:
            return
        last_in = db.get_session(user_key).get("last_in")
        try:
            await ad.send(uid, outs, last_in)
        except Exception as e:  # never crash the webhook / loop because one send failed
            log.warning("send to %s failed: %s", user_key, e)

    async def process(inc: Incoming) -> list:
        outs = engine.handle(inc)
        await deliver(inc.user_key, outs)
        return outs

    async def run_reminders() -> int:
        due = engine.due_reminders()
        for user_key, out in due:
            await deliver(user_key, [out])
        return len(due)

    async def reminder_loop():
        while True:
            try:
                await run_reminders()
            except Exception as e:  # pragma: no cover
                log.exception("reminder loop: %s", e)
            await asyncio.sleep(settings.reminder_interval_s)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(reminder_loop()) if run_scheduler else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Booking bot (WhatsApp + Viber)", lifespan=lifespan)
    app.state.engine = engine
    app.state.adapters = adapters
    app.state.clock = clock
    app.state.run_reminders = run_reminders
    app.state.db = db

    @app.get("/health")
    async def health():
        return {"ok": True}

    # ---------------- WhatsApp Cloud API ----------------
    @app.get("/webhook/whatsapp")
    async def wa_verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and settings.wa_verify_token and \
                q.get("hub.verify_token") == settings.wa_verify_token:
            return PlainTextResponse(q.get("hub.challenge", ""))
        raise HTTPException(403, "verification failed")

    @app.post("/webhook/whatsapp")
    async def wa_webhook(request: Request):
        raw = await request.body()
        ad = adapters["whatsapp"]
        if not ad.verify_signature(raw, {k.lower(): v for k, v in request.headers.items()}):
            raise HTTPException(401, "bad signature")
        for inc in ad.parse(await request.json()):
            await process(inc)
        return {"ok": True}

    # ---------------- Viber ----------------
    @app.post("/webhook/viber")
    async def viber_webhook(request: Request):
        raw = await request.body()
        ad = adapters["viber"]
        if not ad.verify_signature(raw, {k.lower(): v for k, v in request.headers.items()}):
            raise HTTPException(401, "bad signature")
        body = await request.json()
        incs = ad.parse(body)
        if body.get("event") == "conversation_started" and incs:
            outs = engine.handle(incs[0])
            return JSONResponse(ad.welcome(outs))  # Viber shows it as the welcome message
        for inc in incs:
            await process(inc)
        return {"ok": True}

    # ---------------- Emulator (local demo only) ----------------
    if settings.demo_mode:
        emu: EmulatorAdapter = adapters["emulator"]

        @app.get("/")
        async def root():
            return RedirectResponse("/demo/")

        @app.post("/api/emu/send")
        async def emu_send(request: Request):
            body = await request.json()
            inc = emu.parse(body)[0]
            await process(inc)
            return {"messages": emu.drain(inc.user_id), "clock": clock().isoformat(),
                    "local": engine.now_local().strftime("%a %d.%m. %H:%M")}

        @app.post("/api/emu/clock")
        async def emu_clock(request: Request):
            body = await request.json()
            if "set" in body:
                clock.fixed = datetime.fromisoformat(body["set"])
                clock.offset = timedelta()
            clock.offset += timedelta(hours=float(body.get("hours", 0)))
            if body.get("next_reminder"):
                at = engine.next_reminder_at()
                if at:
                    target = at.replace(tzinfo=engine.tz).astimezone(timezone.utc)
                    clock.offset += max(target - clock(), timedelta())
            n = await run_reminders()
            return {"clock": clock().isoformat(), "reminders": n,
                    "local": engine.now_local().strftime("%a %d.%m. %H:%M")}

        @app.get("/api/emu/poll")
        async def emu_poll(user: str):
            return {"messages": emu.drain(user), "clock": clock().isoformat(),
                    "local": engine.now_local().strftime("%a %d.%m. %H:%M")}

        app.mount("/demo", StaticFiles(directory=str(ROOT / "demo"), html=True), name="demo")

    return app


app = create_app()
