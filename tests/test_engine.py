"""Core scenarios, messenger-independent."""
from datetime import timedelta

from app.core.models import Incoming
from app.export import CsvExporter, GoogleSheetsExporter


def book(chat, service="svc:cut_m", master="mst:alex", day=None, slot=None):
    chat.say("Hello")
    chat.tap("menu:book")
    chat.tap(service)
    if master and any(i == master for i in chat.ids()):
        chat.tap(master)
    day = day or next(i for i in chat.ids() if i.startswith("day:"))
    chat.tap(day)
    slot = slot or next(i for i in chat.ids() if i.startswith("slot:"))
    chat.tap(slot)
    assert "ok" in chat.ids()
    chat.tap("ok")
    return day[4:], slot[5:]


def code_of(engine, user="emulator:u1"):
    return engine.db.user_upcoming(user, "0000")[0]["code"]


# ---------------------------------------------------------------- first contact / languages
def test_first_contact_shows_ai_notice_in_three_languages(chat):
    outs = chat.say("?")
    assert "Ich bin ein KI-Assistent" in outs[0].text
    assert "I'm an AI assistant" in outs[0].text
    assert "ИИ-ассистент" in outs[0].text
    assert chat.ids() == ["lang:de", "lang:en", "lang:ru"]


def test_language_detection_and_menu(chat):
    outs = chat.say("Привет, хочу записаться")
    assert "ИИ-ассистент" in outs[0].text
    assert "Ich bin" not in outs[0].text
    assert chat.ids() == ["menu:book", "menu:my", "menu:lang"]
    assert "Записаться" in outs[1].buttons[0].title


def test_german_detection(chat):
    outs = chat.say("Hallo, ich brauche einen Termin")
    assert outs[0].text.startswith("🤖 Ich bin ein KI-Assistent")
    assert outs[1].buttons[0].title == "📅 Termin buchen"


def test_switch_language(chat):
    chat.say("hi")
    chat.tap("menu:lang")
    chat.tap("lang:de")
    assert chat.last[0].text == "Was möchtest du tun?"


def test_every_language_has_every_string():
    from app.core.i18n import LANGS, T
    for key, table in T.items():
        for lg in LANGS:
            assert table.get(lg), f"{key} missing {lg}"


# ---------------------------------------------------------------- booking flow
def test_full_booking_flow(chat, engine):
    chat.say("hi")
    chat.tap("menu:book")
    assert "svc:cut_m" in chat.ids()
    chat.tap("svc:cut_m")
    assert set(chat.ids()) >= {"mst:alex", "mst:mia"}  # both cut men's hair
    chat.tap("mst:alex")
    days = [i for i in chat.ids() if i.startswith("day:")]
    assert days[0] == "day:2026-11-18"  # today still has slots
    chat.tap("day:2026-11-19")  # Thursday: Alex works 12-20
    slots = [i[5:] for i in chat.ids() if i.startswith("slot:")]
    assert slots[0] == "12:00"
    chat.tap("more:1")
    assert any(i.startswith("slot:") for i in chat.ids())
    chat.tap("slot:19:30")  # last 30-min slot before 20:00
    assert "Alex" in chat.text() and "Do" not in chat.text()
    chat.tap("ok")
    assert "Booked" in chat.last[0].text
    b = engine.db.user_upcoming("emulator:u1", "0000")[0]
    assert (b["start"], b["end"], b["master_id"]) == ("2026-11-19T19:30", "2026-11-19T20:00", "alex")


def test_single_master_service_skips_master_step(chat):
    chat.say("hi")
    chat.tap("menu:book")
    chat.tap("svc:nails")  # only Olga
    assert all(i.startswith("day:") or i == "back" for i in chat.ids())
    # Olga works Mon/Wed/Fri/Sat only
    from datetime import date
    for i in chat.ids():
        if i.startswith("day:"):
            assert date.fromisoformat(i[4:]).weekday() in (0, 2, 4, 5)
    chat.tap("back")
    assert "svc:nails" in chat.ids()


def test_booked_slot_disappears_and_overlap_respected(chat, engine):
    book(chat, "svc:color", "mst:mia", "day:2026-11-19", "slot:10:00")  # 90 min -> 10:00-11:30
    free = engine.free_slots("mia", "2026-11-19", "cut_w")  # 60 min
    assert "10:00" not in free and "10:30" not in free and "11:00" not in free
    assert "09:00" in free  # 09:00-10:00 fits
    assert "09:30" not in free  # 09:30-10:30 overlaps
    assert "11:30" in free


def test_no_slots_in_the_past_or_within_lead_time(engine):
    # now 09:00 Berlin, lead time 60 min -> first slot today >= 10:00
    assert engine.free_slots("alex", "2026-11-18", "cut_m")[0] == "10:00"
    assert engine.free_slots("mia", "2026-11-23", "cut_w") == []  # Mia does not work Mondays


def test_slot_taken_by_someone_else(engine):
    from tests.conftest import Chat
    a, b = Chat(engine, "a"), Chat(engine, "b")
    for c in (a, b):
        c.say("hi")
        c.tap("menu:book")
        c.tap("svc:cut_m")
        c.tap("mst:alex")
        c.tap("day:2026-11-19")
        c.tap("slot:12:00")
    a.tap("ok")
    assert "Booked" in a.last[0].text
    b.tap("ok")
    assert "just taken" in b.last[0].text
    assert "slot:12:00" not in b.ids()


def test_back_navigation(chat):
    chat.say("hi")
    chat.tap("menu:book")
    chat.tap("svc:cut_m")
    chat.tap("mst:alex")
    chat.tap("day:2026-11-19")
    chat.tap("slot:12:00")
    chat.tap("back")
    assert "slot:12:00" in chat.ids()
    chat.tap("back")
    assert any(i.startswith("day:") for i in chat.ids())
    chat.tap("back")
    assert "mst:alex" in chat.ids()
    chat.tap("back")
    assert "svc:cut_m" in chat.ids()


def test_typed_number_and_title_work_like_buttons(chat):
    chat.say("hi")
    chat.say("1")  # Book
    assert "svc:cut_m" in chat.ids()
    chat.say("Beard trim · 15 €")
    assert chat.ids()[0].startswith("day:")  # only Alex does beards -> straight to days


def test_unknown_text_repeats_buttons(chat):
    chat.say("hi")
    chat.tap("menu:book")
    outs = chat.say("blabla")
    assert "didn't get that" in outs[0].text
    assert "svc:cut_m" in chat.ids()


def test_non_text_message_is_handled(chat):
    chat.say("hi")
    outs = chat.say("")
    assert outs  # never silent


# ---------------------------------------------------------------- my bookings / cancel / reschedule
def test_cancel(chat, engine):
    book(chat)
    chat.tap("menu:my")
    code = code_of(engine)
    assert f"my:{code}" in chat.ids()
    chat.tap(f"my:{code}")
    chat.tap(f"cancel:{code}")
    assert "cancelled" in chat.last[0].text
    assert engine.db.get_booking(code)["status"] == "cancelled"
    chat.tap("menu:my")
    assert "no upcoming" in chat.last[0].text


def test_reschedule_keeps_code_and_frees_old_slot(chat, engine):
    book(chat, day="day:2026-11-19", slot="slot:12:00")
    code = code_of(engine)
    chat.tap("menu:my")
    chat.tap(f"my:{code}")
    chat.tap(f"resched:{code}")
    assert code in chat.last[0].text
    chat.tap("day:2026-11-20")
    chat.tap("slot:15:00")
    assert "Moved" in chat.last[0].text
    b = engine.db.get_booking(code)
    assert b["start"] == "2026-11-20T15:00" and b["status"] == "active"
    assert "12:00" in engine.free_slots("alex", "2026-11-19", "cut_m")


def test_reschedule_can_pick_overlapping_own_time(chat, engine):
    book(chat, "svc:cut_w", "mst:mia", "day:2026-11-19", "slot:10:00")  # 10:00-11:00
    code = code_of(engine)
    chat.tap(f"resched:{code}")
    chat.tap("day:2026-11-19")
    assert "slot:10:30" in chat.ids()  # own booking ignored while moving


def test_cannot_touch_someone_elses_booking(engine):
    from tests.conftest import Chat
    a, b = Chat(engine, "a"), Chat(engine, "b")
    book(a)
    code = code_of(engine, "emulator:a")
    b.say("hi")
    b.tap(f"cancel:{code}")
    assert engine.db.get_booking(code)["status"] == "active"


# ---------------------------------------------------------------- reminders
def test_reminders_24h_and_2h_once_each(chat, engine, clock):
    book(chat, day="day:2026-11-20", slot="slot:15:00")  # Fri 15:00 Berlin = 14:00 UTC
    assert engine.due_reminders() == []
    clock.fixed = clock.fixed.replace(day=19, hour=13, minute=59)  # 24h01m before
    assert engine.due_reminders() == []
    clock.fixed = clock.fixed.replace(hour=14, minute=0)
    due = engine.due_reminders()
    assert len(due) == 1 and "Reminder" in due[0][1].text
    assert due[0][1].template.name == "appointment_reminder_24h"
    assert [b.id.split(":")[0] for b in due[0][1].buttons] == ["keep", "resched", "cancel"]
    assert engine.due_reminders() == []  # not twice
    clock.fixed = clock.fixed.replace(day=20, hour=12, minute=0)
    due = engine.due_reminders()
    assert len(due) == 1 and "In 2 hours" in due[0][1].text
    assert engine.due_reminders() == []


def test_reminder_buttons_work(chat, engine, clock):
    book(chat, day="day:2026-11-20", slot="slot:15:00")
    clock.fixed = clock.fixed.replace(day=19, hour=14)
    (_, msg), = engine.due_reminders()
    chat.tap(msg.buttons[0].id)
    assert "see you" in chat.last[0].text.lower()
    chat.tap(msg.buttons[2].id)
    assert "cancelled" in chat.last[0].text


def test_late_booking_gets_no_24h_reminder(chat, engine, clock):
    book(chat, day="day:2026-11-18", slot="slot:16:00")  # today, 7 h ahead
    assert engine.due_reminders() == []
    clock.fixed = clock.fixed + timedelta(hours=5, minutes=1)  # 14:01 Berlin, 1h59 left
    due = engine.due_reminders()
    assert len(due) == 1 and "2 hours" in due[0][1].text


def test_cancelled_booking_gets_no_reminder(chat, engine, clock):
    book(chat, day="day:2026-11-20", slot="slot:15:00")
    chat.tap(f"cancel:{code_of(engine)}")
    clock.fixed = clock.fixed.replace(day=19, hour=14)
    assert engine.due_reminders() == []


def test_rescheduled_booking_resets_reminders(chat, engine, clock):
    book(chat, day="day:2026-11-20", slot="slot:15:00")
    code = code_of(engine)
    clock.fixed = clock.fixed.replace(day=19, hour=14)
    assert len(engine.due_reminders()) == 1
    chat.tap(f"resched:{code}")
    chat.tap("day:2026-11-25")
    chat.tap("slot:15:00")
    clock.fixed = clock.fixed.replace(day=24, hour=14)
    assert len(engine.due_reminders()) == 1


def test_reminder_language_follows_user(engine, clock):
    from tests.conftest import Chat
    c = Chat(engine, "de1")
    c.say("Hallo")
    book(c, day="day:2026-11-20", slot="slot:15:00")
    clock.fixed = clock.fixed.replace(day=19, hour=14)
    (_, msg), = engine.due_reminders()
    assert msg.text.startswith("⏰ Erinnerung") and msg.template.lang == "de"


# ---------------------------------------------------------------- admin
def test_admin_day_close_open(engine):
    from tests.conftest import Chat
    client, admin = Chat(engine, "c"), Chat(engine, "admin")
    book(client, day="day:2026-11-19", slot="slot:12:00")
    admin.say("/day alex 2026-11-19")
    assert "12:00–12:30" in admin.text() and "Men's haircut" in admin.text()
    admin.say("/close Alex 2026-11-19 13:00")
    assert "Closed" in admin.text()
    assert "13:00" not in engine.free_slots("alex", "2026-11-19", "cut_m")
    admin.say("/day alex 2026-11-19")
    assert "13:00  ⛔ closed" in admin.text()
    admin.say("/open alex 2026-11-19 13:00")
    assert "13:00" in engine.free_slots("alex", "2026-11-19", "cut_m")


def test_admin_close_blocks_long_service(engine):
    engine.admin("/close mia 2026-11-19 11:00")
    free = engine.free_slots("mia", "2026-11-19", "color")  # 90 min
    assert "10:00" not in free and "10:30" not in free and "11:00" not in free
    assert "09:30" in free and "11:30" in free


def test_admin_errors_and_help(engine):
    assert "Unknown master" in engine.admin("/day bob")
    assert "Format" in engine.admin("/close alex 2026-13-40 10:00")
    assert "grid" in engine.admin("/close alex 2026-11-19 10:15")
    assert "/day" in engine.admin("/help")
    assert "free day" in engine.admin("/day olga 2026-11-18")


def test_non_admin_cannot_use_admin_commands(chat, engine):
    chat.say("hi")
    chat.say("/close alex 2026-11-19 12:00")
    assert "12:00" in engine.free_slots("alex", "2026-11-19", "cut_m")


# ---------------------------------------------------------------- export
def test_csv_export(tmp_path, chat, engine):
    engine.exporter = CsvExporter(str(tmp_path / "b.csv"))
    book(chat)
    chat.tap(f"cancel:{code_of(engine)}")
    rows = (tmp_path / "b.csv").read_text().splitlines()
    assert rows[0].startswith("event,code")
    assert rows[1].startswith("booked,") and rows[2].startswith("cancelled,")


def test_google_sheets_stub_and_broken_exporter(chat, engine):
    g = GoogleSheetsExporter("sheet", "creds.json")
    engine.exporter = g
    book(chat)
    assert g.pending[0][0] == "booked"

    class Boom:
        def export(self, *a):
            raise RuntimeError("sheets down")

    engine.exporter = Boom()
    chat.tap("menu:book")
    chat.tap("svc:beard")
    chat.tap(next(i for i in chat.ids() if i.startswith("day:")))
    chat.tap(next(i for i in chat.ids() if i.startswith("slot:")))
    chat.tap("ok")
    assert "Booked" in chat.last[0].text  # export failure never breaks booking


def test_session_persists_between_messages(engine):
    engine.handle(Incoming("emulator", "p", text="hi"))
    s = engine.db.get_session("emulator:p")
    assert s["lang"] == "en" and s["state"] == "menu" and s["last_in"]


def test_next_reminder_at_for_demo_clock(chat, engine, clock):
    assert engine.next_reminder_at() is None
    book(chat, day="day:2026-11-20", slot="slot:15:00")
    from datetime import datetime
    assert engine.next_reminder_at() == datetime(2026, 11, 19, 15, 0)
    clock.fixed = clock.fixed.replace(day=19, hour=14)
    engine.due_reminders()
    assert engine.next_reminder_at() == datetime(2026, 11, 20, 13, 0)
