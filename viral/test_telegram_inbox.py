#!/usr/bin/env python3
"""Test telegram_inbox.py against a fake Telegram on this computer. Never calls the real Telegram.

  python3 viral/test_telegram_inbox.py
"""
import json, os, shutil, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir))
TOKEN, GOOD, OTHER = "FAKETOKEN", 4242, 999
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
UPDATES = [
    {"update_id": 100, "message": {"message_id": 1, "date": 1700000000, "chat": {"id": GOOD}, "from": {"first_name": "Tester"},
     "text": "look at this https://example.com/video/1 so good", "entities": [{"type": "url", "offset": 13, "length": 27}]}},
    {"update_id": 101, "message": {"message_id": 2, "date": 1700000100, "chat": {"id": OTHER}, "text": "spam https://evil.example"}},
    {"update_id": 102, "message": {"message_id": 3, "date": 1700000200, "chat": {"id": GOOD}, "caption": "screenshot of a hook",
     "photo": [{"file_id": "small", "file_size": 10, "width": 10, "height": 10}, {"file_id": "big", "file_size": 99, "width": 100, "height": 100}]}},
]


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json"):
        self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        q = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        if f"/bot{TOKEN}/getUpdates" in self.path:
            off = int(q.get("offset", 0))
            self.server.offsets.append(off)
            return self._send(json.dumps({"ok": True, "result": [u for u in UPDATES if u["update_id"] >= off]}).encode())
        if f"/bot{TOKEN}/getFile" in self.path:
            return self._send(json.dumps({"ok": True, "result": {"file_path": "photos/" + q["file_id"] + ".png"}}).encode())
        self.send_response(404); self.end_headers()

    def do_GET(self):
        if self.path == f"/file/bot{TOKEN}/photos/big.png":
            return self._send(PNG, "image/png")
        self.send_response(404); self.end_headers()


def run(root, port, extra=()):
    env = dict(os.environ, CONTENT_FACTORY_ROOT=root, TELEGRAM_API_BASE=f"http://127.0.0.1:{port}")
    return subprocess.run([sys.executable, os.path.join(HERE, "telegram_inbox.py"), "--brand", "testbrand", "--once", *extra],
                          env=env, capture_output=True, text=True, timeout=60)


def main():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    srv.offsets = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    root = tempfile.mkdtemp(prefix="cf-telegram-test-")
    fails = []

    def expect(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond: fails.append(msg)
    try:
        b = os.path.join(root, "brands", "testbrand")
        os.makedirs(os.path.join(b, "viral", "inbox"))
        json.dump({"brand": "Test"}, open(os.path.join(b, "brand.json"), "w"))
        with open(os.path.join(root, ".env"), "w") as f:
            f.write(f"TELEGRAM_BOT_TOKEN_TESTBRAND={TOKEN}\nTELEGRAM_ALLOWED_CHAT_ID_TESTBRAND={GOOD}\n")
        inbox = os.path.join(b, "viral", "inbox")
        r = run(root, port)
        expect(r.returncode == 0, f"first run exits 0 {r.stderr.strip()[:200]}")
        folders = sorted(d for d in os.listdir(inbox) if os.path.isdir(os.path.join(inbox, d)))
        expect(len(folders) == 2, f"two folders saved (others ignored): {folders}")
        m1 = json.load(open(os.path.join(inbox, folders[0], "message.json")))
        expect(m1["links"] == ["https://example.com/video/1"], f"link captured: {m1['links']}")
        m2 = json.load(open(os.path.join(inbox, folders[1], "message.json")))
        expect(m2["screenshots"] == ["screenshot-1.png"] and os.path.getsize(os.path.join(inbox, folders[1], "screenshot-1.png")) == len(PNG),
               "screenshot downloaded")
        expect("evil.example" not in "".join(open(os.path.join(inbox, d, "message.json")).read() for d in folders), "other chat ignored")
        off = json.load(open(os.path.join(inbox, "offset.json")))["offset"]
        expect(off == 103, f"offset kept in inbox folder ({off})")
        r2 = run(root, port)
        folders2 = sorted(d for d in os.listdir(inbox) if os.path.isdir(os.path.join(inbox, d)))
        expect(folders2 == folders, "second run collects nothing new")
        expect(srv.offsets[-1] == 103, f"second run asked for offset 103 ({srv.offsets[-1]})")
        expect(TOKEN not in (r.stdout + r.stderr + r2.stdout + r2.stderr), "token never printed")
        os.remove(os.path.join(root, ".env"))
        r3 = run(root, port)
        expect(r3.returncode != 0 and "TELEGRAM_BOT_TOKEN_TESTBRAND" in r3.stderr, "missing .env gives a clear message")
    finally:
        srv.shutdown()
        shutil.rmtree(root, ignore_errors=True)
    print("ALL PASSED" if not fails else f"{len(fails)} FAILED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
