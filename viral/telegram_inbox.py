#!/usr/bin/env python3
"""Collect posts you share to a private Telegram bot, so they can be broken down later.

  python3 viral/telegram_inbox.py --brand NAME           keep listening (Ctrl+C to stop)
  python3 viral/telegram_inbox.py --brand NAME --once    collect everything waiting, then exit

Reads TELEGRAM_BOT_TOKEN_<BRAND> and TELEGRAM_ALLOWED_CHAT_ID_<BRAND> from .env (BRAND is the brand name in capitals
with dashes turned into underscores, e.g. example-brand -> EXAMPLE_BRAND). Messages from any other chat are ignored.
Each share is saved as brands/NAME/viral/inbox/<timestamp>/ with message.json (links, text) and any screenshots.
The update offset lives in the inbox folder (offset.json), so nothing is collected twice.
Python standard library only. Uses Telegram getUpdates long polling."""
import argparse, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "engine"))
import paths  # noqa: E402

API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
URL_RE = re.compile(r"https?://[^\s<>\"']+")
IMAGE_MIME = ("image/",)


def env_key(brand):
    return re.sub(r"[^A-Za-z0-9]+", "_", brand).upper()


def read_env(path):
    """Tiny .env reader: KEY=value lines, optional quotes, # comments."""
    out = {}
    if not os.path.exists(path): return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
        out[k.strip()] = v
    return out


class Api:
    def __init__(self, token):
        self.token = token

    def _open(self, url, data=None, timeout=60):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as ex:
            raise RuntimeError(f"Telegram answered HTTP {ex.code}") from None     # never print the URL: it holds the token
        except (urllib.error.URLError, OSError) as ex:
            raise RuntimeError(f"could not reach Telegram ({getattr(ex, 'reason', ex)})") from None

    def call(self, method, params=None, timeout=60):
        data = urllib.parse.urlencode(params or {}).encode()
        res = json.loads(self._open(f"{API_BASE}/bot{self.token}/{method}", data, timeout))
        if not res.get("ok"): raise RuntimeError(f"Telegram said no to {method}: {res.get('description')}")
        return res["result"]

    def download(self, file_path):
        return self._open(f"{API_BASE}/file/bot{self.token}/{file_path}", timeout=120)


def links_in(msg):
    text = msg.get("text") or msg.get("caption") or ""
    ents = msg.get("entities") or msg.get("caption_entities") or []
    found = []
    for e in ents:
        if e.get("type") == "text_link" and e.get("url"): found.append(e["url"])
        elif e.get("type") == "url":
            raw = text.encode("utf-16-le")                              # Telegram counts offsets in UTF-16 units
            found.append(raw[e["offset"] * 2:(e["offset"] + e["length"]) * 2].decode("utf-16-le", "ignore"))
    found += URL_RE.findall(text)
    seen, out = set(), []
    for u in found:
        u = u.rstrip(".,)")
        if u and u not in seen: seen.add(u); out.append(u)
    return out


def folder_for(inbox, msg, state):
    gid = msg.get("media_group_id")
    if gid and gid in state["groups"] and os.path.isdir(os.path.join(inbox, state["groups"][gid])):
        return state["groups"][gid]
    stamp = datetime.fromtimestamp(msg.get("date", time.time()), timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{msg.get('message_id', 0)}"
    if gid: state["groups"][gid] = name
    return name


def image_file_ids(msg):
    ids = []
    if msg.get("photo"):
        best = max(msg["photo"], key=lambda p: p.get("file_size", 0) or p.get("width", 0))
        ids.append((best["file_id"], ".jpg"))
    doc = msg.get("document")
    if doc and str(doc.get("mime_type", "")).startswith(IMAGE_MIME):
        ext = os.path.splitext(doc.get("file_name", ""))[1].lower() or ".jpg"
        ids.append((doc["file_id"], ext if re.match(r"^\.[a-z0-9]{2,5}$", ext) else ".jpg"))
    return ids


def save_message(api, inbox, msg, state):
    name = folder_for(inbox, msg, state)
    folder = os.path.join(inbox, name)
    os.makedirs(folder, exist_ok=True)
    mpath = os.path.join(folder, "message.json")
    data = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {
        "received": datetime.now(timezone.utc).isoformat(timespec="seconds"), "message_ids": [], "text": "",
        "links": [], "screenshots": [], "from": None, "processed": False}
    data["message_ids"].append(msg.get("message_id"))
    text = msg.get("text") or msg.get("caption") or ""
    if text: data["text"] = (data["text"] + "\n" + text).strip()
    for u in links_in(msg):
        if u not in data["links"]: data["links"].append(u)
    fwd = msg.get("forward_origin") or {}
    if fwd: data["forwarded_from"] = fwd.get("sender_user_name") or (fwd.get("chat") or {}).get("title") or fwd.get("type")
    sender = msg.get("from") or {}
    data["from"] = sender.get("first_name") or sender.get("username")
    for fid, ext in image_file_ids(msg):
        try:
            info = api.call("getFile", {"file_id": fid})
            got = os.path.splitext(info.get("file_path", ""))[1].lower()
            if re.match(r"^\.[a-z0-9]{2,5}$", got): ext = got        # trust the extension Telegram stored the file under
            fname = f"screenshot-{len(data['screenshots']) + 1}{ext}"
            with open(os.path.join(folder, fname), "wb") as f:
                f.write(api.download(info["file_path"]))
            data["screenshots"].append(fname)
        except RuntimeError as ex:
            print(f"  could not download an image ({ex})", file=sys.stderr)
    paths.save_json(mpath, data, indent=2)
    return name


def main():
    ap = argparse.ArgumentParser(description="Collect shared posts from a private Telegram bot.")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--once", action="store_true", help="collect what is waiting, then exit")
    ap.add_argument("--wait", type=int, default=30, help="seconds to wait for news when listening (default 30)")
    a = ap.parse_args()
    paths.load_brand(a.brand)
    env = dict(read_env(paths.env_file()))
    key = env_key(a.brand)
    token = os.environ.get(f"TELEGRAM_BOT_TOKEN_{key}") or env.get(f"TELEGRAM_BOT_TOKEN_{key}")
    chat = os.environ.get(f"TELEGRAM_ALLOWED_CHAT_ID_{key}") or env.get(f"TELEGRAM_ALLOWED_CHAT_ID_{key}")
    if not token or not chat:
        paths.die(f"Missing settings. Add these two lines to .env (copy .env.example if you have no .env):\n"
                  f"  TELEGRAM_BOT_TOKEN_{key}=...\n  TELEGRAM_ALLOWED_CHAT_ID_{key}=...")
    inbox = paths.inbox_dir(a.brand)
    os.makedirs(inbox, exist_ok=True)
    opath = os.path.join(inbox, "offset.json")
    state = paths.load_json(opath, {}) or {}
    state.setdefault("offset", 0)
    state.setdefault("groups", {})
    api = Api(token)
    saved = ignored = 0
    print(f"Listening for {a.brand}" + (" (once)" if a.once else " (Ctrl+C to stop)"))
    try:
        while True:
            try:
                updates = api.call("getUpdates", {"offset": state["offset"], "timeout": 0 if a.once else a.wait,
                                                   "allowed_updates": json.dumps(["message"])},
                                   timeout=(a.wait + 30))
            except RuntimeError as ex:
                if a.once: paths.die(f"Stopped: {ex}", 1)
                print(f"  problem: {ex}; trying again in 10 seconds", file=sys.stderr)
                time.sleep(10)
                continue
            for u in updates:
                msg = u.get("message")
                if msg and str((msg.get("chat") or {}).get("id")) == str(chat).strip():
                    name = save_message(api, inbox, msg, state)
                    saved += 1
                    print(f"  saved {name}")
                else:
                    ignored += 1                      # another chat: not saved, but drained so it is not seen again
                state["offset"] = u["update_id"] + 1
                paths.save_json(opath, state, indent=2)
            if a.once and not updates:
                break
    except KeyboardInterrupt:
        print("\nStopped.")
    print(f"Done: {saved} saved, {ignored} ignored (other chats or unsupported)")


if __name__ == "__main__":
    main()
