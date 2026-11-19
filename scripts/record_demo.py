"""Record the portfolio video (demo.mp4) and 3 screenshots from the local emulator.

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
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8090/demo/"
W, H = 1440, 900

CURSOR_JS = """
(() => {
  const c = document.createElement('div');
  c.id = '__cursor';
  Object.assign(c.style, {position:'fixed', left:'0px', top:'0px', width:'22px', height:'22px', borderRadius:'50%',
    background:'rgba(255,255,255,.85)', border:'2px solid rgba(0,0,0,.55)', zIndex: 99999, pointerEvents:'none',
    transform:'translate(-50%,-50%)', transition:'width .12s, height .12s, background .12s',
    boxShadow:'0 2px 8px rgba(0,0,0,.35)'});
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(c));
  if (document.body) document.body.appendChild(c);
  window.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; });
  window.addEventListener('mousedown', () => { c.style.width = c.style.height = '16px'; c.style.background = 'rgba(0,168,132,.9)'; });
  window.addEventListener('mouseup', () => { c.style.width = c.style.height = '22px'; c.style.background = 'rgba(255,255,255,.85)'; });
})();
"""


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bookingvid_"))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        ctx.add_init_script(CURSOR_JS)
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
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H,
                                          "everyNthFrame": 1})
        page.wait_for_timeout(900)
        page.mouse.move(W / 2, H / 2)

        client = page.locator("#p-client")
        admin = page.locator("#p-admin")

        def shot(name):
            page.evaluate("document.getElementById('__cursor').style.display='none'")
            page.screenshot(path=str(ROOT / name))
            page.evaluate("document.getElementById('__cursor').style.display=''")

        def step(n):
            page.evaluate(f"window.demo.setStep({n})")

        def click(loc, pause=350):
            loc.scroll_into_view_if_needed()
            box = loc.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
            page.wait_for_timeout(120)
            page.mouse.down()
            page.wait_for_timeout(70)
            page.mouse.up()
            page.wait_for_timeout(pause)

        def wait_bot(phone, n_bubbles_before, extra=700):
            phone.locator(".row.in .bubble:not(:has(.typing))").nth(n_bubbles_before).wait_for()
            page.wait_for_timeout(extra)

        def count(phone):
            return phone.locator(".row.in .bubble:not(:has(.typing))").count()

        def type_send(phone, text):
            inp = phone.locator("input")
            click(inp, 150)
            inp.type(text, delay=45)
            page.wait_for_timeout(250)
            click(phone.locator(".send"), 100)

        def pick_list(phone, row_text):
            """Answer the latest bot message: reply button if it has buttons, else open its list."""
            last = phone.locator(".row.in .msg").last
            if last.locator(".listbtn").count():
                click(last.locator(".listbtn"), 550)
                click(phone.locator(".sheet .opt", has_text=row_text).first, 200)
            else:
                click(last.locator(".btn", has_text=row_text).first)

        def bot_reply(phone, before, extra=900):
            wait_bot(phone, before, extra)

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
            click(client.locator(".btn", has_text=re.compile(r"\sBook$")).last)
            bot_reply(client, n)
            click(client.locator(".listbtn").last, 800)
            shot("screenshot-1-services.png")
            page.wait_for_timeout(400)
            n = count(client)
            click(client.locator(".sheet .opt", has_text="Men's haircut").first, 200)
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
            click(client.locator(".btn", has_text="Confirm").last)
            bot_reply(client, n + 1, 1400)
            page.mouse.move(W - 40, H - 40, steps=12)
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
            page.mouse.move(W - 40, H - 40, steps=10)
            page.wait_for_timeout(300)
            shot("screenshot-3-reminder-admin.png")

            # 7. reschedule from the reminder
            step(7)
            n = count(client)
            click(client.locator(".btn", has_text="Reschedule").last)
            bot_reply(client, n)
            n = count(client)
            pick_list(client, "Fri 20.11")
            bot_reply(client, n)
            n = count(client)
            pick_list(client, "14:00")
            bot_reply(client, n + 1, 1800)

            page.mouse.move(W - 40, H - 40, steps=10)
            page.wait_for_timeout(2500)

        except Exception:
            page.screenshot(path=str(tmp.parent / 'record_fail.png'))
            print('FAILED, screenshot:', tmp.parent / 'record_fail.png')
            raise
        cdp.send("Page.stopScreencast")
        page.wait_for_timeout(300)
        ctx.close()
        browser.close()

    # screencast frames come only when the page changes -> concat with real durations, resample to 30 fps
    lst = tmp / "frames.txt"
    with lst.open("w") as f:
        for i, (ts, path) in enumerate(frames):
            dur = (frames[i + 1][0] - ts) if i + 1 < len(frames) else 2.0
            f.write(f"file '{path}'\nduration {max(dur, 0.001):.4f}\n")
        f.write(f"file '{frames[-1][1]}'\n")
    out = ROOT / "demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"fps=30,scale={W}:{H}:flags=lanczos,format=yuv420p", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "18", "-movflags", "+faststart", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("saved", out)


if __name__ == "__main__":
    sys.exit(main())
