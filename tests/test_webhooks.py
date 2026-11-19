"""WhatsApp Cloud API + Viber adapters through the real FastAPI webhooks, HTTP mocked."""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

from app.adapters import viber as vb_mod
from app.adapters import whatsapp as wa_mod
from app.core.models import Button, Out, Template

USER = "491701234567"


def wa_body(msg: dict, frm=USER):
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "123456"},
        "contacts": [{"wa_id": frm, "profile": {"name": "Anna"}}],
        "messages": [{"from": frm, "id": "wamid.X", "timestamp": "1763452800", **msg}]}}]}]}


def wa_post(tc, body, secret="app-secret"):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return tc.post("/webhook/whatsapp", content=raw,
                   headers={"content-type": "application/json", "x-hub-signature-256": sig})


def wa_text(tc, text, frm=USER):
    return wa_post(tc, wa_body({"type": "text", "text": {"body": text}}, frm))


def wa_tap(tc, button_id, kind="button_reply", frm=USER):
    return wa_post(tc, wa_body({"type": "interactive",
                                "interactive": {"type": kind, kind: {"id": button_id, "title": "x"}}}, frm))


def vb_post(tc, body, token="viber-token"):
    raw = json.dumps(body).encode()
    sig = hmac.new(token.encode(), raw, hashlib.sha256).hexdigest()
    return tc.post("/webhook/viber", content=raw,
                   headers={"content-type": "application/json", "x-viber-content-signature": sig})


def vb_msg(text, uid="vb-user=="):
    return {"event": "message", "timestamp": 1, "message_token": 2,
            "sender": {"id": uid, "name": "Ivan", "language": "ru"},
            "message": {"type": "text", "text": text}}


# ================================================================ WhatsApp
def test_wa_verify_handshake(api):
    tc, *_ = api
    r = tc.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                            "hub.challenge": "1158201444"})
    assert r.status_code == 200 and r.text == "1158201444"
    r = tc.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong",
                                            "hub.challenge": "x"})
    assert r.status_code == 403


def test_wa_rejects_bad_signature(api):
    tc, _, wa, _ = api
    r = wa_post(tc, wa_body({"type": "text", "text": {"body": "hi"}}), secret="evil")
    assert r.status_code == 401
    assert wa.calls == []


def test_wa_first_message_sends_text_and_buttons(api):
    tc, _, wa, _ = api
    assert wa_text(tc, "Hello").status_code == 200
    assert len(wa.calls) == 2
    first, second = wa.calls
    assert first["url"] == "https://graph.facebook.com/v23.0/123456/messages"
    assert first["headers"]["authorization"] == "Bearer WA_TEST_TOKEN"
    assert first["json"]["type"] == "text" and "I'm an AI assistant" in first["json"]["text"]["body"]
    assert first["json"]["to"] == USER and first["json"]["messaging_product"] == "whatsapp"
    inter = second["json"]["interactive"]
    assert inter["type"] == "button"
    assert [b["reply"]["id"] for b in inter["action"]["buttons"]] == ["menu:book", "menu:my", "menu:lang"]


def test_wa_full_booking_over_webhook(api):
    tc, app, wa, _ = api
    wa_text(tc, "Hello")
    wa.calls.clear()
    wa_tap(tc, "menu:book")
    lst = wa.calls[-1]["json"]["interactive"]
    assert lst["type"] == "list"  # 5 services + back -> list message
    rows = lst["action"]["sections"][0]["rows"]
    assert len(rows) <= 10 and all(len(r["title"]) <= 24 for r in rows)
    assert len(lst["action"]["button"]) <= 20
    wa_tap(tc, "svc:cut_m", "list_reply")
    wa_tap(tc, "mst:alex", "list_reply")
    wa_tap(tc, "day:2026-11-19", "list_reply")
    wa_tap(tc, "slot:12:00", "list_reply")
    confirm = wa.calls[-1]["json"]["interactive"]
    assert confirm["type"] == "button" and "Alex" in confirm["body"]["text"]
    wa_tap(tc, "ok")
    assert "Booked" in wa.calls[-2]["json"]["text"]["body"]
    rows = app.state.db.user_upcoming(f"whatsapp:{USER}", "0000")
    assert rows[0]["start"] == "2026-11-19T12:00"


def test_wa_long_titles_go_to_list_with_description():
    out = Out("x", [Button("a", "A very long service title that exceeds"), Button("b", "B")])
    p = wa_mod.render(out, USER)
    row = p["interactive"]["action"]["sections"][0]["rows"][0]
    assert p["interactive"]["type"] == "list"
    assert len(row["title"]) == 24 and row["description"].startswith("A very long")


def test_wa_reminder_outside_window_uses_template(api, clock):
    tc, app, wa, _ = api
    wa_text(tc, "Hello")
    for p in ("menu:book", "svc:cut_m", "mst:alex", "day:2026-11-20", "slot:15:00", "ok"):
        wa_tap(tc, p)
    wa.calls.clear()
    clock.fixed = clock.fixed.replace(day=19, hour=14)  # 30 h after last message -> window closed
    n = asyncio.run(app.state.run_reminders())
    assert n == 1
    p = wa.calls[0]["json"]
    assert p["type"] == "template"
    assert p["template"]["name"] == "appointment_reminder_24h"
    assert p["template"]["language"]["code"] == "en"
    body, *btns = p["template"]["components"]
    assert body["parameters"][1]["text"] == "Alex"
    assert [b["parameters"][0]["payload"].split(":")[0] for b in btns] == ["keep", "resched", "cancel"]
    # the client taps the template quick reply "Cancel"
    code = btns[2]["parameters"][0]["payload"]
    wa.calls.clear()
    wa_post(tc, wa_body({"type": "button", "button": {"payload": code, "text": "Cancel"}}))
    assert "cancelled" in wa.calls[0]["json"]["text"]["body"]


def test_wa_reminder_inside_window_uses_interactive(api, clock):
    tc, app, wa, _ = api
    wa_text(tc, "Hello")
    for p in ("menu:book", "svc:cut_m", "mst:alex", "day:2026-11-18", "slot:16:00", "ok"):
        wa_tap(tc, p)
    wa.calls.clear()
    clock.fixed = clock.fixed.replace(hour=13, minute=1)  # 1h59 before, user wrote 5h ago
    asyncio.run(app.state.run_reminders())
    p = wa.calls[0]["json"]
    assert p["type"] == "interactive" and "2 hours" in p["interactive"]["body"]["text"]


def test_wa_admin_command(api):
    tc, _, wa, _ = api
    wa_text(tc, "/day alex 2026-11-19", frm="491700000001")
    assert "Alex" in wa.calls[-1]["json"]["text"]["body"]
    wa.calls.clear()
    wa_text(tc, "/close alex 2026-11-19 12:00", frm="491799999999")  # not an admin
    assert "Closed" not in json.dumps(wa.calls)


def test_wa_status_and_media_events(api):
    tc, _, wa, _ = api
    status = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "statuses": [{"id": "wamid.X", "status": "delivered"}]}}]}]}
    assert wa_post(tc, status).status_code == 200
    assert wa.calls == []
    wa_text(tc, "hi")
    wa.calls.clear()
    wa_post(tc, wa_body({"type": "image", "image": {"id": "1"}}))
    assert "didn't get that" in wa.calls[0]["json"]["text"]["body"]


def test_wa_send_error_does_not_crash_webhook(clock):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    def fail(request):
        return httpx.Response(400, json={"error": {"message": "Recipient not in allowed list"}})

    s = Settings()
    s.db_path = ":memory:"
    s.wa_app_secret = ""
    app = create_app(s, wa_client=httpx.AsyncClient(transport=httpx.MockTransport(fail)), clock=clock,
                     run_scheduler=False)
    with TestClient(app) as tc:
        r = tc.post("/webhook/whatsapp", json=wa_body({"type": "text", "text": {"body": "hi"}}))
        assert r.status_code == 200  # Meta must get 200, otherwise it retries


# ================================================================ Viber
def test_viber_rejects_bad_signature(api):
    tc, *_ = api
    r = vb_post(tc, vb_msg("hi"), token="wrong")
    assert r.status_code == 401


def test_viber_webhook_event(api):
    tc, *_ = api
    assert vb_post(tc, {"event": "webhook", "timestamp": 1}).status_code == 200


def test_viber_conversation_started_returns_welcome(api):
    tc, _, _, vb = api
    r = vb_post(tc, {"event": "conversation_started", "user": {"id": "vb1==", "name": "Ivan"},
                     "subscribed": False})
    data = r.json()
    assert "I'm an AI assistant" in data["text"] and "Ich bin ein KI-Assistent" in data["text"]
    assert [b["ActionBody"] for b in data["keyboard"]["Buttons"]] == ["#lang:de", "#lang:en", "#lang:ru"]
    assert vb.calls == []  # answered in the HTTP response, no API call


def test_viber_booking_flow(api):
    tc, app, _, vb = api
    vb_post(tc, vb_msg("Привет"))
    assert "ИИ-ассистент" in vb.calls[0]["json"]["text"]
    assert vb.calls[0]["url"] == "https://chatapi.viber.com/pa/send_message"
    assert vb.calls[0]["headers"]["x-viber-auth-token"] == "viber-token"
    kb = vb.calls[1]["json"]["keyboard"]
    assert kb["Buttons"][0]["ActionBody"] == "#menu:book"
    for p in ("menu:book", "svc:cut_w", "mst:mia", "day:2026-11-19", "slot:10:00", "ok"):
        vb_post(tc, vb_msg("#" + p))
    assert "Готово" in vb.calls[-2]["json"]["text"]
    assert app.state.db.user_upcoming("viber:vb-user==", "0000")[0]["master_id"] == "mia"


def test_viber_typed_text_is_not_payload(api):
    tc, _, _, vb = api
    vb_post(tc, vb_msg("hi"))
    vb.calls.clear()
    vb_post(tc, vb_msg("1"))  # typed "1" = first option (Book)
    assert "Which service" in vb.calls[0]["json"]["text"]


def test_viber_reminder_is_plain_message(api, clock):
    tc, app, _, vb = api
    vb_post(tc, vb_msg("hi"))
    for p in ("menu:book", "svc:cut_m", "mst:alex", "day:2026-11-20", "slot:15:00", "ok"):
        vb_post(tc, vb_msg("#" + p))
    vb.calls.clear()
    clock.fixed = clock.fixed.replace(day=19, hour=14)
    asyncio.run(app.state.run_reminders())
    p = vb.calls[0]["json"]
    assert "Reminder" in p["text"] and p["receiver"] == "vb-user=="
    assert [b["ActionBody"].split(":")[0] for b in p["keyboard"]["Buttons"]] == ["#keep", "#resched", "#cancel"]


def test_viber_api_error_status_raises():
    async def run():
        def handler(req):
            return httpx.Response(200, json={"status": 6, "status_message": "notSubscribed"})
        ad = vb_mod.ViberAdapter("t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await ad.send("u", [Out("hi")])
    with pytest.raises(RuntimeError, match="notSubscribed"):
        asyncio.run(run())


def test_viber_many_buttons_two_columns():
    out = Out("x", [Button(str(i), f"B{i}") for i in range(6)])
    kb = vb_mod.keyboard(out)
    assert all(b["Columns"] == 3 for b in kb["Buttons"])
    assert vb_mod.keyboard(Out("x")) is None


# ================================================================ Emulator API
def test_emulator_api_and_time_travel(api):
    tc, *_ = api
    r = tc.post("/api/emu/send", json={"user": "demo", "text": "Hello"})
    msgs = r.json()["messages"]
    assert msgs[0]["text"]["body"].startswith("🤖 I'm an AI assistant")
    for p in ("menu:book", "svc:cut_m", "mst:alex", "day:2026-11-20", "slot:15:00", "ok"):
        tc.post("/api/emu/send", json={"user": "demo", "payload": p})
    r = tc.post("/api/emu/clock", json={"hours": 30})
    assert r.json()["reminders"] == 1
    polled = tc.get("/api/emu/poll", params={"user": "demo"}).json()["messages"]
    assert polled[0]["_template"] == "appointment_reminder_24h"


def test_emulator_admin(api):
    tc, *_ = api
    r = tc.post("/api/emu/send", json={"user": "admin", "text": "/day mia 2026-11-19"})
    assert "Mia" in r.json()["messages"][0]["text"]["body"]


def test_template_payload_shape():
    out = Out("r", [Button("keep:AB12", "ok")], template=Template("appointment_reminder_2h", "de", ["a", "b"]))
    p = wa_mod.render(out, USER, use_template=True)
    assert p["template"]["components"][1] == {"type": "button", "sub_type": "quick_reply", "index": "0",
                                              "parameters": [{"type": "payload", "payload": "keep:AB12"}]}
