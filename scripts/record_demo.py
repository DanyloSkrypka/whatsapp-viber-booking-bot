"""Record the portfolio video (demo.mp4, 1080p60) and 4 screenshots (docs/screenshots/) from the local emulator.

Needs the server running on 127.0.0.1:8090 with a fresh DB, e.g.:
    DB_PATH=/tmp/demo.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090
Then:
    .venv/bin/python scripts/record_demo.py
Uses the installed Google Chrome (channel="chrome") and records frames through the Chrome
DevTools screencast + system ffmpeg, so no Playwright browser/ffmpeg download is needed.
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8090/demo/?theme=dark"  # Demo Showcase kit: light or dark
W, H = 1920, 1080
SHOTS = ROOT / "docs" / "screenshots"



def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bookingvid_"))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--disable-gpu-vsync", "--disable-frame-rate-limit"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = ctx.new_page()
        frames: list[tuple[float, Path]] = []
        cdp = ctx.new_cdp_session(page)

        def on_frame(ev):
            f = tmp / f"f{len(frames):05d}.jpg"
            f.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ev["metadata"]["timestamp"], f))
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_frame)
        # fixed demo clock: Wednesday 18.11.2026, 09:00 Berlin
        page.request.post("http://127.0.0.1:8090/api/emu/clock", data={"set": "2026-11-18T08:00:00+00:00"})
        page.goto(URL)
        page.wait_for_timeout(600)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "maxWidth": W, "maxHeight": H,
                                          "everyNthFrame": 1})
        page.wait_for_timeout(900)

        client = page.locator("#p-client")
        admin = page.locator("#p-admin")

        def shot(name):
            page.screenshot(path=str(SHOTS / name))

        def step(n):
            page.evaluate(f"window.demo.setStep({n})")

        def click(loc, pause=350):
            """No cursor in the video: soft tap ripple on the element, then a real DOM click."""
            loc.scroll_into_view_if_needed()
            loc.evaluate("el => window.demo.tap(el)")
            page.wait_for_timeout(220)
            loc.evaluate("el => el.click()")
            page.wait_for_timeout(pause)

        def wait_bot(phone, n_bubbles_before, extra=700):
            phone.locator(".ds-group--in .ds-bubble:not(.ds-bubble--typing)").nth(n_bubbles_before).wait_for()
            page.wait_for_timeout(extra)

        def count(phone):
            return phone.locator(".ds-group--in .ds-bubble:not(.ds-bubble--typing)").count()

        def type_send(phone, text):
            inp = phone.locator("input")
            inp.evaluate("el => el.focus()")
            page.wait_for_timeout(150)
            inp.type(text, delay=45)
            page.wait_for_timeout(250)
            click(phone.locator(".ds-composer__send"), 100)

        def pick_list(phone, row_text):
            """Answer the latest bot message: reply button if it has buttons, else open its list."""
            last = phone.locator(".ds-group--in .ds-msg").last
            if last.locator(".ds-listbtn").count():
                click(last.locator(".ds-listbtn"), 550)
                click(phone.locator(".ds-sheet :is(.ds-option, .ds-slot)", has_text=row_text).first, 200)
            else:
                click(last.locator(".ds-kb__btn", has_text=row_text).first)

        def bot_reply(phone, before, extra=900):
            wait_bot(phone, before, extra)

        SHOTS.mkdir(parents=True, exist_ok=True)
        page.set_default_timeout(10000)
        try:
            # 1. greeting + AI disclosure
            step(1)
            n = count(client)
            type_send(client, "Hi! I need a haircut")
            bot_reply(client, n + 1, 1600)

            # 2. book -> service -> master
            step(2)
            n = count(client)
            click(client.locator(".ds-kb__btn", has_text=re.compile(r"\sBook$")).last)
            bot_reply(client, n)
            click(client.locator(".ds-listbtn").last, 800)
            shot("screenshot-1-services.png")
            page.wait_for_timeout(400)
            n = count(client)
            click(client.locator(".ds-sheet :is(.ds-option, .ds-slot)", has_text="Men's haircut").first, 200)
            bot_reply(client, n)
            n = count(client)
            pick_list(client, "Alex")
            bot_reply(client, n)

            # 3. free days + slots
            step(3)
            n = count(client)
            pick_list(client, "Thu 19.11")
            bot_reply(client, n)
            n = count(client)
            pick_list(client, "12:30")
            bot_reply(client, n, 1200)

            # 4. confirm
            step(4)
            n = count(client)
            click(client.locator(".ds-kb__btn", has_text="Confirm").last)
            bot_reply(client, n + 1, 1400)
            page.wait_for_timeout(500)
            shot("screenshot-2-booked.png")

            # 5. time travel to the 24h reminder
            step(5)
            n = count(client)
            click(page.locator("#jump"), 200)
            bot_reply(client, n, 2200)

            # 6. admin
            step(6)
            n = count(admin)
            type_send(admin, "/day alex 2026-11-19")
            bot_reply(admin, n, 1600)
            n = count(admin)
            type_send(admin, "/close alex 2026-11-19 16:00")
            bot_reply(admin, n, 1400)
            page.wait_for_timeout(300)
            shot("screenshot-3-reminder-admin.png")

            # 7. reschedule from the reminder
            step(7)
            n = count(client)
            click(client.locator(".ds-kb__btn", has_text="Reschedule").last)
            bot_reply(client, n)
            n = count(client)
            pick_list(client, "Fri 20.11")
            bot_reply(client, n)
            n = count(client)
            pick_list(client, "14:00")
            bot_reply(client, n + 1, 1000)

            page.wait_for_timeout(1500)
            page.evaluate("window.demo.endCard()")
            page.wait_for_timeout(4000)
            shot("04-end-card.png")

        except Exception:
            page.screenshot(path=str(tmp.parent / 'record_fail.png'))
            print('FAILED, screenshot:', tmp.parent / 'record_fail.png')
            raise
        end_ts = time.time()
        cdp.send("Page.stopScreencast")
        page.wait_for_timeout(300)
        ctx.close()
        browser.close()

    # screencast frames come only when the page changes, at irregular times -> resample them
    # ourselves onto an exact 60 fps grid (latest frame at each tick) and pipe to ffmpeg
    out = ROOT / "demo.mp4"
    fps = 60
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps),
                             "-c:v", "mjpeg", "-i", "-", "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p",
                             "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-r", str(fps),
                             "-movflags", "+faststart", "-an", str(out)], stdin=subprocess.PIPE)
    t0, j = frames[0][0], 0
    for k in range(int((end_ts - t0) * fps) + 1):
        t = t0 + k / fps
        while j + 1 < len(frames) and frames[j + 1][0] <= t + 1e-4:
            j += 1
        gap = frames[j + 1][0] - frames[j][0] if j + 1 < len(frames) else 0
        if 1.5 / fps < gap < 4.5 / fps and t - frames[j][0] >= 0.5 / fps:
            # Chrome dropped frames in the middle of an animation: fill the hole with a weighted
            # blend of the neighbours instead of holding the old frame (no visible hitch)
            w = (t - frames[j][0]) / gap
            proc.stdin.write(subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(frames[j][1]), "-i", str(frames[j + 1][1]), "-filter_complex",
                 f"blend=all_expr='A*{1 - w:.3f}+B*{w:.3f}'", "-q:v", "1", "-f", "mjpeg", "-"], capture_output=True, check=True).stdout)
            continue
        proc.stdin.write(frames[j][1].read_bytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    shutil.rmtree(tmp, ignore_errors=True)
    print("saved", out)


if __name__ == "__main__":
    sys.exit(main())
