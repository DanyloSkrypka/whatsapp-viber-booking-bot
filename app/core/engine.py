"""Booking dialog engine. Knows nothing about WhatsApp or Viber: text + buttons in, Out messages out."""
from __future__ import annotations

import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .db import DB
from .i18n import ADMIN_HELP, LANGS, WEEKDAYS, detect_lang, t
from .models import Button, Incoming, Out, Template

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PAGE = 9  # WhatsApp list: max 10 rows -> 9 options + "More"
GREETINGS = {"hi", "hello", "hey", "hallo", "moin", "servus", "привет", "здравствуйте", "start", "/start",
             "menu", "menü", "меню"}
FMT = "%Y-%m-%dT%H:%M"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Engine:
    def __init__(self, db: DB, salon: dict, tz: str = "Europe/Berlin",
                 clock: Callable[[], datetime] = utcnow, admins: Optional[list[str]] = None,
                 exporter=None):
        self.db = db
        self.salon = salon
        self.tz = ZoneInfo(tz)
        self.clock = clock
        self.admins = set(admins or [])
        self.exporter = exporter
        self.services = {s["id"]: s for s in salon["services"]}
        self.masters = {m["id"]: m for m in salon["masters"]}
        self.step = int(salon.get("slot_step_min", 30))

    # ------------------------------------------------------------------ time helpers
    def now_local(self) -> datetime:
        return self.clock().astimezone(self.tz).replace(tzinfo=None)

    def fmt_when(self, start: str, lang: str) -> str:
        d = datetime.strptime(start, FMT)
        return f"{WEEKDAYS[lang][d.weekday()]} {d:%d.%m.} {d:%H:%M}"

    def fmt_day(self, day: str, lang: str) -> str:
        d = datetime.strptime(day, "%Y-%m-%d")
        return f"{WEEKDAYS[lang][d.weekday()]} {d:%d.%m}"

    # ------------------------------------------------------------------ availability
    def free_slots(self, master_id: str, day: str, service_id: str, ignore_code: Optional[str] = None) -> list[str]:
        m = self.masters[master_id]
        d = datetime.strptime(day, "%Y-%m-%d")
        hours = m["hours"].get(DAY_KEYS[d.weekday()])
        if not hours:
            return []
        dur = timedelta(minutes=self.services[service_id]["duration"])
        step = timedelta(minutes=self.step)
        open_t = datetime.strptime(f"{day}T{hours[0]}", FMT)
        close_t = datetime.strptime(f"{day}T{hours[1]}", FMT)
        earliest = self.now_local() + timedelta(minutes=int(self.salon.get("min_lead_min", 60)))
        busy: list[tuple[datetime, datetime]] = []
        for b in self.db.bookings_for_master_day(master_id, day):
            if b["code"] != ignore_code:
                busy.append((datetime.strptime(b["start"], FMT), datetime.strptime(b["end"], FMT)))
        for s in self.db.blocks_for_master_day(master_id, day):
            st = datetime.strptime(s, FMT)
            busy.append((st, st + step))
        out = []
        cur = open_t
        while cur + dur <= close_t:
            if cur >= earliest and all(cur + dur <= a or cur >= b for a, b in busy):
                out.append(cur.strftime("%H:%M"))
            cur += step
        return out

    def free_days(self, master_id: str, service_id: str, ignore_code: Optional[str] = None) -> list[str]:
        today = self.now_local().date()
        days = []
        for i in range(int(self.salon.get("booking_horizon_days", 14))):
            day = (today + timedelta(days=i)).isoformat()
            if self.free_slots(master_id, day, service_id, ignore_code):
                days.append(day)
        return days

    # ------------------------------------------------------------------ entry point
    def handle(self, msg: Incoming) -> list[Out]:
        with self.db.lock:
            s = self.db.get_session(msg.user_key)
            s["last_in"] = self.clock().isoformat()
            try:
                return self._handle(msg, s)
            finally:
                self.db.save_session(s)

    def _handle(self, msg: Incoming, s: dict) -> list[Out]:
        text = (msg.text or "").strip()
        payload = msg.payload

        if text.startswith("/") and text.lower() not in GREETINGS:
            if msg.user_key in self.admins:
                return [Out(self.admin(text))]

        # first contact: AI disclosure (EU AI Act art. 50) + language
        if s["state"] == "new" or not s["lang"]:
            lang = detect_lang(text)
            if lang and not payload:
                s["lang"] = lang
                return [Out(t("ai_notice", lang, salon=self.salon["name"]))] + [self.menu(s)]
            if not (payload or "").startswith("lang:"):
                s["state"] = "lang"
                notice = "\n".join(t("ai_notice", lg, salon=self.salon["name"]) for lg in ("de", "en", "ru"))
                return [Out(notice), self.lang_picker(s)]

        # free text -> button id (number or exact title of the last shown options)
        if not payload and text:
            payload = self.match_option(s, text)
            if payload is None and text.lower() in GREETINGS:
                return [self.menu(s)]
            if payload is None:
                return [Out(t("not_understood", s["lang"]))] + self.repeat(s)

        return self.on_payload(s, payload or "")

    def match_option(self, s: dict, text: str) -> Optional[str]:
        opts = s["data"].get("opts", [])
        low = text.lower()
        if low.isdigit() and 1 <= int(low) <= len(opts):
            return opts[int(low) - 1][0]
        for oid, title in opts:
            plain = re.sub(r"^[^\wа-яё]+", "", title.lower()).strip()
            if low == title.lower() or low == plain:
                return oid
        return None

    def repeat(self, s: dict) -> list[Out]:
        last = s["data"].get("last_out")
        if last:
            return [Out(last["text"], [Button(*b) for b in last["buttons"]], last.get("list_title"))]
        return [self.menu(s)]

    def remember(self, s: dict, out: Out) -> Out:
        s["data"]["opts"] = [[b.id, b.title] for b in out.buttons]
        s["data"]["last_out"] = {"text": out.text, "buttons": s["data"]["opts"], "list_title": out.list_title}
        return out

    # ------------------------------------------------------------------ screens
    def lang_picker(self, s: dict) -> Out:
        s["state"] = "lang"
        return self.remember(s, Out(t("choose_lang", s["lang"] or "en"),
                                    [Button("lang:de", "Deutsch"), Button("lang:en", "English"),
                                     Button("lang:ru", "Русский")]))

    def menu(self, s: dict) -> Out:
        s["state"] = "menu"
        lg = s["lang"]
        return self.remember(s, Out(t("menu", lg), [Button("menu:book", t("btn_book", lg)),
                                                     Button("menu:my", t("btn_my", lg)),
                                                     Button("menu:lang", t("btn_lang", lg))]))

    def paged(self, s: dict, text: str, items: list[Button], page: int, back: bool = True) -> Out:
        lg = s["lang"]
        chunk = items[page * PAGE:(page + 1) * PAGE]
        btns = list(chunk)
        if (page + 1) * PAGE < len(items):
            btns.append(Button(f"more:{page + 1}", t("btn_more", lg)))
        elif back and len(btns) < 10:
            btns.append(Button("back", t("btn_back", lg)))
        s["data"]["page"] = page
        return self.remember(s, Out(text, btns, list_title=t("btn_choose", lg)))

    def services_screen(self, s: dict, page: int = 0) -> Out:
        s["state"] = "svc"
        lg = s["lang"]
        items = [Button(f"svc:{sv['id']}", f"{sv['name'][lg]} · {sv['price']}") for sv in self.salon["services"]]
        return self.paged(s, t("choose_service", lg), items, page)

    def masters_screen(self, s: dict) -> Out:
        s["state"] = "mst"
        lg = s["lang"]
        svc = self.services[s["data"]["service"]]
        items = [Button(f"mst:{m['id']}", m["name"]) for m in self.salon["masters"] if svc["id"] in m["services"]]
        return self.paged(s, t("choose_master", lg, service=svc["name"][lg]), items, 0)

    def days_screen(self, s: dict, page: int = 0, code: Optional[str] = None) -> Out:
        lg = s["lang"]
        d = s["data"]
        days = self.free_days(d["master"], d["service"], ignore_code=code)
        if not days:
            return self.remember(s, Out(t("no_days", lg), [Button("back", t("btn_back", lg)),
                                                            Button("menu", t("btn_menu", lg))]))
        items = [Button(f"day:{x}", self.fmt_day(x, lg)) for x in days]
        title = (t("reschedule_pick_day", lg, code=code) if code
                 else t("choose_day", lg, master=self.masters[d["master"]]["name"]))
        s["state"] = "resched_day" if code else "day"
        return self.paged(s, title, items, page)

    def slots_screen(self, s: dict, page: int = 0) -> Out:
        lg = s["lang"]
        d = s["data"]
        code = d.get("resched")
        slots = self.free_slots(d["master"], d["day"], d["service"], ignore_code=code)
        s["state"] = "resched_slot" if code else "slot"
        items = [Button(f"slot:{x}", x) for x in slots]
        return self.paged(s, t("choose_slot", lg, day=self.fmt_day(d["day"], lg)), items, page)

    def confirm_screen(self, s: dict) -> Out:
        s["state"] = "confirm"
        lg = s["lang"]
        d = s["data"]
        svc = self.services[d["service"]]
        text = t("summary", lg, service=svc["name"][lg], price=svc["price"],
                 master=self.masters[d["master"]]["name"], when=self.fmt_when(f"{d['day']}T{d['slot']}", lg))
        return self.remember(s, Out(text, [Button("ok", t("btn_confirm", lg)), Button("back", t("btn_back", lg))]))

    def booking_text(self, key: str, b, lg: str) -> str:
        return t(key, lg, code=b["code"], service=self.services[b["service_id"]]["name"][lg],
                 master=self.masters[b["master_id"]]["name"], when=self.fmt_when(b["start"], lg))

    def booking_actions(self, s: dict, b) -> Out:
        s["state"] = "booking"
        lg = s["lang"]
        return self.remember(s, Out(self.booking_text("booking_actions", b, lg), [
            Button(f"resched:{b['code']}", t("btn_reschedule", lg)),
            Button(f"cancel:{b['code']}", t("btn_cancel", lg)),
            Button("menu", t("btn_menu", lg))]))

    # ------------------------------------------------------------------ transitions
    def on_payload(self, s: dict, p: str) -> list[Out]:
        d = s["data"]
        lg = s["lang"] or "en"
        kind, _, arg = p.partition(":")

        if kind == "lang" and arg in LANGS:
            s["lang"] = arg
            return [self.menu(s)]
        if p == "menu" or s["lang"] is None:
            return [self.menu(s)]
        if p == "menu:lang":
            return [self.lang_picker(s)]
        if p == "menu:book":
            s["data"] = {}
            return [self.services_screen(s)]
        if p == "menu:my":
            return [self.my_bookings(s)]
        if kind == "more":
            page = int(arg)
            return [{"svc": lambda: self.services_screen(s, page),
                     "day": lambda: self.days_screen(s, page),
                     "resched_day": lambda: self.days_screen(s, page, d.get("resched")),
                     "slot": lambda: self.slots_screen(s, page),
                     "resched_slot": lambda: self.slots_screen(s, page)}.get(s["state"], lambda: self.menu(s))()]
        if p == "back":
            return [self.back(s)]
        if kind == "svc" and arg in self.services:
            d["service"] = arg
            masters = [m for m in self.salon["masters"] if arg in m["services"]]
            if len(masters) == 1:  # skip the choice if only one master does it
                d["master"] = masters[0]["id"]
                d["auto_master"] = True
                return [self.days_screen(s)]
            d.pop("auto_master", None)
            return [self.masters_screen(s)]
        if kind == "mst" and arg in self.masters and d.get("service"):
            d["master"] = arg
            return [self.days_screen(s)]
        if kind == "day" and d.get("master"):
            d["day"] = arg
            return [self.slots_screen(s)]
        if kind == "slot" and d.get("day"):
            if arg not in self.free_slots(d["master"], d["day"], d["service"], d.get("resched")):
                return [Out(t("slot_taken", lg)), self.slots_screen(s)]
            d["slot"] = arg
            if d.get("resched"):
                return self.do_reschedule(s)
            return [self.confirm_screen(s)]
        if p == "ok" and s["state"] == "confirm":
            return self.do_book(s)
        if kind == "my":
            b = self.db.get_booking(arg)
            if b and b["user_key"] == s["user_key"]:
                return [self.booking_actions(s, b)]
        if kind in ("cancel", "resched", "keep"):
            b = self.db.get_booking(arg)
            if not b or b["user_key"] != s["user_key"] or b["status"] != "active" \
                    or b["start"] <= self.now_local().strftime(FMT):
                return [Out(t("too_late", lg)), self.menu(s)]
            if kind == "keep":
                return [Out(t("keep_ok", lg))]
            if kind == "cancel":
                self.db.cancel_booking(arg)
                self.export("cancelled", arg)
                s["data"] = {}
                return [Out(self.booking_text("cancelled", b, lg)), self.menu(s)]
            s["data"] = {"resched": arg, "service": b["service_id"], "master": b["master_id"]}
            return [self.days_screen(s, code=arg)]
        return [Out(t("not_understood", lg))] + self.repeat(s)

    def back(self, s: dict) -> Out:
        st = s["state"]
        d = s["data"]
        if st == "confirm":
            return self.slots_screen(s)
        if st in ("slot", "resched_slot"):
            return self.days_screen(s, code=d.get("resched"))
        if st == "day":
            return self.services_screen(s) if d.get("auto_master") else self.masters_screen(s)
        if st == "mst":
            return self.services_screen(s)
        if st == "resched_day":
            b = self.db.get_booking(d["resched"])
            return self.booking_actions(s, b)
        return self.menu(s)

    def my_bookings(self, s: dict) -> Out:
        lg = s["lang"]
        rows = self.db.user_upcoming(s["user_key"], self.now_local().strftime(FMT))
        if not rows:
            return self.remember(s, Out(t("no_bookings", lg), [Button("menu:book", t("btn_book", lg)),
                                                                Button("menu", t("btn_menu", lg))]))
        s["state"] = "my"
        items = [Button(f"my:{b['code']}",
                        f"{self.fmt_when(b['start'], lg)} {self.services[b['service_id']]['name'][lg]}")
                 for b in rows[:9]]
        return self.paged(s, t("my_bookings", lg), items, 0)

    def _new_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(4))
            if not self.db.get_booking(code):
                return code

    def _span(self, d: dict) -> tuple[str, str]:
        start = datetime.strptime(f"{d['day']}T{d['slot']}", FMT)
        end = start + timedelta(minutes=self.services[d["service"]]["duration"])
        return start.strftime(FMT), end.strftime(FMT)

    def _presuppress_reminders(self, code: str, start: str) -> None:
        """Booked less than 24h / 2h ahead -> that reminder makes no sense."""
        left = datetime.strptime(start, FMT) - self.now_local()
        if left <= timedelta(hours=24):
            self.db.mark_reminded(code, "24")
        if left <= timedelta(hours=2):
            self.db.mark_reminded(code, "2")

    def do_book(self, s: dict) -> list[Out]:
        d = s["data"]
        lg = s["lang"]
        if d["slot"] not in self.free_slots(d["master"], d["day"], d["service"]):
            return [Out(t("slot_taken", lg)), self.slots_screen(s)]
        start, end = self._span(d)
        code = self._new_code()
        self.db.insert_booking(code, s["user_key"], d["service"], d["master"], start, end, self.clock().isoformat())
        self._presuppress_reminders(code, start)
        b = self.db.get_booking(code)
        self.export("booked", code)
        s["data"] = {}
        return [Out(self.booking_text("booked", b, lg)), self.menu(s)]

    def do_reschedule(self, s: dict) -> list[Out]:
        d = s["data"]
        lg = s["lang"]
        code = d["resched"]
        start, end = self._span(d)
        self.db.move_booking(code, start, end)
        self._presuppress_reminders(code, start)
        b = self.db.get_booking(code)
        self.export("rescheduled", code)
        s["data"] = {}
        return [Out(self.booking_text("rescheduled", b, lg)), self.menu(s)]

    def export(self, event: str, code: str) -> None:
        if self.exporter:
            b = self.db.get_booking(code)
            try:
                self.exporter.export(event, dict(b))
            except Exception:  # export must never break the dialog
                pass

    # ------------------------------------------------------------------ reminders
    def due_reminders(self) -> list[tuple[str, Out]]:
        """Return (user_key, message) for every reminder that is due now, and mark them sent."""
        out = []
        with self.db.lock:
            now = self.now_local()
            rows = self.db.active_between(now.strftime(FMT), (now + timedelta(hours=24)).strftime(FMT))
            for b in rows:
                left = datetime.strptime(b["start"], FMT) - now
                which = None
                if left <= timedelta(hours=2) and not b["reminded_2"]:
                    which = "2"
                elif left > timedelta(hours=2) and not b["reminded_24"]:
                    which = "24"
                if not which:
                    continue
                s = self.db.get_session(b["user_key"])
                lg = s["lang"] or "en"
                svc = self.services[b["service_id"]]["name"][lg]
                master = self.masters[b["master_id"]]["name"]
                when = self.fmt_when(b["start"], lg)
                key = "reminder_24" if which == "24" else "reminder_2"
                msg = Out(self.booking_text(key, b, lg), [
                    Button(f"keep:{b['code']}", t("btn_keep", lg)),
                    Button(f"resched:{b['code']}", t("btn_reschedule", lg)),
                    Button(f"cancel:{b['code']}", t("btn_cancel", lg))],
                    template=Template(f"appointment_reminder_{which}h", lg, [svc, master, when, b["code"]]))
                self.db.mark_reminded(b["code"], which)
                if which == "2":
                    self.db.mark_reminded(b["code"], "24")
                s["data"]["opts"] = [[x.id, x.title] for x in msg.buttons]
                self.db.save_session(s)
                out.append((b["user_key"], msg))
        return out

    def next_reminder_at(self) -> Optional[datetime]:
        """Local time of the next pending reminder (used by the demo 'time travel' button)."""
        now = self.now_local()
        best = None
        for b in self.db.active_between(now.strftime(FMT), "9999"):
            st = datetime.strptime(b["start"], FMT)
            for flag, hrs in (("reminded_24", 24), ("reminded_2", 2)):
                if not b[flag]:
                    at = max(st - timedelta(hours=hrs), now)
                    best = at if best is None or at < best else best
                    break
        return best

    # ------------------------------------------------------------------ admin
    def _master(self, name: str) -> Optional[str]:
        name = name.lower()
        for m in self.salon["masters"]:
            if m["id"] == name or m["name"].lower() == name:
                return m["id"]
        return None

    def admin(self, text: str) -> str:
        parts = text.split()
        cmd = parts[0].lower()
        if cmd == "/day" and len(parts) >= 2:
            mid = self._master(parts[1])
            if not mid:
                return "Unknown master. Masters: " + ", ".join(m["name"] for m in self.salon["masters"])
            day = parts[2] if len(parts) > 2 else self.now_local().date().isoformat()
            try:
                date.fromisoformat(day)
            except ValueError:
                return "Date format: YYYY-MM-DD"
            rows = self.db.bookings_for_master_day(mid, day)
            blocks = self.db.blocks_for_master_day(mid, day)
            n = len(rows)
            lines = [f"📋 {self.masters[mid]['name']} — {self.fmt_day(day, 'en')}: {n} booking{'s' if n != 1 else ''}"]
            for b in rows:
                svc = self.services[b["service_id"]]["name"]["en"]
                lines.append(f"{b['start'][11:]}–{b['end'][11:]}  {svc}  #{b['code']}")
            for st in sorted(blocks):
                lines.append(f"{st[11:]}  ⛔ closed")
            if len(lines) == 1:
                lines.append("— free day —")
            return "\n".join(lines)
        if cmd in ("/close", "/open") and len(parts) == 4:
            mid = self._master(parts[1])
            if not mid:
                return "Unknown master."
            try:
                st = datetime.strptime(f"{parts[2]}T{parts[3]}", FMT)
            except ValueError:
                return "Format: /close <master> YYYY-MM-DD HH:MM"
            if st.minute % self.step:
                return f"Time must be on a {self.step}-minute grid."
            key = st.strftime(FMT)
            if cmd == "/close":
                self.db.add_block(mid, key)
                return f"⛔ Closed {self.masters[mid]['name']} {self.fmt_when(key, 'en')}"
            self.db.remove_block(mid, key)
            return f"✅ Reopened {self.masters[mid]['name']} {self.fmt_when(key, 'en')}"
        return ADMIN_HELP


def load_salon(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
