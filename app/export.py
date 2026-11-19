"""Optional booking export. The engine only knows the BookingExporter interface.

- NullExporter     : default, does nothing.
- CsvExporter      : appends rows to a local CSV (works offline, good for demos).
- GoogleSheetsExporter : stub. Plug in gspread / Sheets API with a service account
  (GOOGLE_CREDENTIALS_FILE + GOOGLE_SHEET_ID) when a client wants it.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

COLUMNS = ["event", "code", "user_key", "service_id", "master_id", "start", "end", "status"]


class BookingExporter(Protocol):
    def export(self, event: str, booking: dict) -> None: ...


class NullExporter:
    def export(self, event: str, booking: dict) -> None:
        return None


class CsvExporter:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, event: str, booking: dict) -> None:
        new = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(COLUMNS)
            w.writerow([event] + [booking.get(c, "") for c in COLUMNS[1:]])


class GoogleSheetsExporter:
    """Interface stub: same rows as CsvExporter, target = a Google Sheet.

    Real implementation (not shipped in the demo, needs client's Google service account):
        gc = gspread.service_account(filename=credentials_file)
        ws = gc.open_by_key(sheet_id).sheet1
        ws.append_row([event, booking["code"], ...], value_input_option="USER_ENTERED")
    """

    def __init__(self, sheet_id: str, credentials_file: str):
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self.pending: list[list[str]] = []  # rows that would be appended

    def export(self, event: str, booking: dict) -> None:
        self.pending.append([event] + [str(booking.get(c, "")) for c in COLUMNS[1:]])


def make_exporter(kind: str, **kw) -> BookingExporter:
    if kind == "csv":
        return CsvExporter(kw.get("path", "data/bookings.csv"))
    if kind == "google":
        return GoogleSheetsExporter(kw.get("sheet_id", ""), kw.get("credentials_file", ""))
    return NullExporter()
