"""All user-facing texts in DE / EN / RU. Keys are shared by every messenger."""
from __future__ import annotations

LANGS = ("de", "en", "ru")
DEFAULT_LANG = "en"

WEEKDAYS = {
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
}

T: dict[str, dict[str, str]] = {
    # EU AI Act art. 50: the user must know they talk to an AI system.
    "ai_notice": {
        "de": "🤖 Ich bin ein KI-Assistent von {salon}. Ich helfe dir, einen Termin zu buchen.",
        "en": "🤖 I'm an AI assistant of {salon}. I can book an appointment for you.",
        "ru": "🤖 Я ИИ-ассистент салона {salon}. Помогу записаться на приём.",
    },
    "choose_lang": {
        "de": "Bitte wähle deine Sprache:",
        "en": "Please choose your language:",
        "ru": "Выберите язык:",
    },
    "menu": {
        "de": "Was möchtest du tun?",
        "en": "What would you like to do?",
        "ru": "Что сделать?",
    },
    "btn_book": {"de": "📅 Termin buchen", "en": "📅 Book", "ru": "📅 Записаться"},
    "btn_my": {"de": "🗂 Meine Termine", "en": "🗂 My bookings", "ru": "🗂 Мои записи"},
    "btn_lang": {"de": "🌐 Sprache", "en": "🌐 Language", "ru": "🌐 Язык"},
    "btn_back": {"de": "↩️ Zurück", "en": "↩️ Back", "ru": "↩️ Назад"},
    "btn_menu": {"de": "🏠 Menü", "en": "🏠 Menu", "ru": "🏠 Меню"},
    "btn_confirm": {"de": "✅ Bestätigen", "en": "✅ Confirm", "ru": "✅ Подтвердить"},
    "btn_cancel": {"de": "❌ Stornieren", "en": "❌ Cancel", "ru": "❌ Отменить"},
    "btn_reschedule": {"de": "🔁 Verschieben", "en": "🔁 Reschedule", "ru": "🔁 Перенести"},
    "btn_keep": {"de": "👍 Ich komme", "en": "👍 I'll be there", "ru": "👍 Приду"},
    "btn_more": {"de": "➡️ Weitere", "en": "➡️ More", "ru": "➡️ Ещё"},
    "btn_choose": {"de": "Auswählen", "en": "Choose", "ru": "Выбрать"},
    "choose_service": {
        "de": "Welche Leistung möchtest du?",
        "en": "Which service would you like?",
        "ru": "Какая услуга нужна?",
    },
    "choose_master": {
        "de": "Bei wem? ({service})",
        "en": "With whom? ({service})",
        "ru": "К какому мастеру? ({service})",
    },
    "choose_day": {
        "de": "Wähle einen Tag bei {master}:",
        "en": "Pick a day with {master}:",
        "ru": "Выберите день у мастера {master}:",
    },
    "choose_slot": {
        "de": "Freie Zeiten am {day}:",
        "en": "Free times on {day}:",
        "ru": "Свободное время {day}:",
    },
    "no_days": {
        "de": "Leider keine freien Termine in den nächsten 2 Wochen.",
        "en": "Sorry, no free slots in the next 2 weeks.",
        "ru": "К сожалению, свободных окон на 2 недели вперёд нет.",
    },
    "summary": {
        "de": "Bitte prüfen:\n💇 {service} ({price})\n👤 {master}\n🗓 {when}",
        "en": "Please check:\n💇 {service} ({price})\n👤 {master}\n🗓 {when}",
        "ru": "Проверьте:\n💇 {service} ({price})\n👤 {master}\n🗓 {when}",
    },
    "booked": {
        "de": "✅ Gebucht! Nr. {code}\n{service} bei {master}, {when}.\nIch erinnere dich 24 h und 2 h vorher.",
        "en": "✅ Booked! No. {code}\n{service} with {master}, {when}.\nI'll remind you 24 h and 2 h before.",
        "ru": "✅ Готово! Запись № {code}\n{service}, мастер {master}, {when}.\nНапомню за 24 ч и за 2 ч.",
    },
    "slot_taken": {
        "de": "😕 Diese Zeit wurde gerade vergeben. Bitte wähle eine andere:",
        "en": "😕 That time was just taken. Please pick another one:",
        "ru": "😕 Это время только что заняли. Выберите другое:",
    },
    "no_bookings": {
        "de": "Du hast keine anstehenden Termine.",
        "en": "You have no upcoming bookings.",
        "ru": "Предстоящих записей нет.",
    },
    "my_bookings": {
        "de": "Deine Termine — wähle einen:",
        "en": "Your bookings — pick one:",
        "ru": "Ваши записи — выберите:",
    },
    "booking_actions": {
        "de": "Nr. {code}: {service} bei {master}, {when}.",
        "en": "No. {code}: {service} with {master}, {when}.",
        "ru": "№ {code}: {service}, {master}, {when}.",
    },
    "cancelled": {
        "de": "❌ Termin Nr. {code} storniert. Bis bald!",
        "en": "❌ Booking No. {code} cancelled. See you!",
        "ru": "❌ Запись № {code} отменена. До встречи!",
    },
    "rescheduled": {
        "de": "🔁 Verschoben! Nr. {code}: {service} bei {master}, {when}.",
        "en": "🔁 Moved! No. {code}: {service} with {master}, {when}.",
        "ru": "🔁 Перенесено! № {code}: {service}, {master}, {when}.",
    },
    "reschedule_pick_day": {
        "de": "Neuer Tag für Nr. {code}:",
        "en": "New day for No. {code}:",
        "ru": "Новый день для записи № {code}:",
    },
    "reminder_24": {
        "de": "⏰ Erinnerung: morgen {when} — {service} bei {master} (Nr. {code}).",
        "en": "⏰ Reminder: tomorrow {when} — {service} with {master} (No. {code}).",
        "ru": "⏰ Напоминание: завтра {when} — {service}, мастер {master} (№ {code}).",
    },
    "reminder_2": {
        "de": "⏰ In 2 Stunden: {when} — {service} bei {master}. Wir freuen uns auf dich!",
        "en": "⏰ In 2 hours: {when} — {service} with {master}. See you soon!",
        "ru": "⏰ Через 2 часа: {when} — {service}, мастер {master}. Ждём вас!",
    },
    "keep_ok": {
        "de": "👍 Super, bis dann!",
        "en": "👍 Great, see you then!",
        "ru": "👍 Отлично, ждём!",
    },
    "not_understood": {
        "de": "Das habe ich nicht verstanden. Bitte nutze die Buttons 👇",
        "en": "Sorry, I didn't get that. Please use the buttons 👇",
        "ru": "Не понял. Пожалуйста, нажмите кнопку 👇",
    },
    "too_late": {
        "de": "Dieser Termin ist schon vorbei oder storniert.",
        "en": "This booking is already over or cancelled.",
        "ru": "Эта запись уже прошла или отменена.",
    },
}

ADMIN_HELP = (
    "🛠 Admin:\n"
    "/day <master> [YYYY-MM-DD] — bookings of the day\n"
    "/close <master> <YYYY-MM-DD> <HH:MM> — close a slot\n"
    "/open <master> <YYYY-MM-DD> <HH:MM> — reopen a slot"
)


def t(key: str, lang: str, **kw: object) -> str:
    table = T[key]
    text = table.get(lang) or table[DEFAULT_LANG]
    return text.format(**kw) if kw else text


def detect_lang(text: str | None) -> str | None:
    """Very small guess from the first message; the user can always switch."""
    if not text:
        return None
    low = text.lower()
    if any("а" <= ch <= "я" or ch == "ё" for ch in low):
        return "ru"
    if any(w in low for w in ("hallo", "termin", "guten", "moin", "servus", "ä", "ö", "ü", "ß")):
        return "de"
    if any(w in low for w in ("hello", "hi", "hey", "book", "appointment")):
        return "en"
    return None
