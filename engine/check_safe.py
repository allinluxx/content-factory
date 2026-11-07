#!/usr/bin/env python3
"""Check that nothing private is about to be pushed. Run it any time:  python3 engine/check_safe.py

It looks at the files git would push (tracked and staged files). Before git exists it walks the folder instead,
skipping everything .gitignore ignores. It FAILS (exit 1) on:
  - an image or video file anywhere except example-brand/
  - any file over 10MB (the font is allowed)
  - anything under brands/ except brands/.gitkeep
  - a path to a home folder on someone's computer
  - something that looks like a key or token (Telegram bot token, sk-..., gho_..., ghp_...)
The pre-push hook runs this, so a failing check stops the push."""
import os, re, subprocess, sys

ROOT = os.path.abspath(os.environ.get("CONTENT_FACTORY_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
MEDIA = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".svg", ".ico", ".avif",
         ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".wmv"}
MAX_BYTES = 10 * 1024 * 1024
FONT_OK = "fonts/TikTokSans-Variable.ttf"
# built from pieces so this file does not trip its own scan
HOME = "/" + "Users" + "/"
PATTERNS = [
    ("home folder path", re.compile(r"(?:/" + "Users" + r"/|/" + "home" + r"/|[A-Za-z]:\\" + "Users" + r"\\)[A-Za-z0-9._-]+")),
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("secret key (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("GitHub token (gho_)", re.compile(r"\bgho_[A-Za-z0-9]{20,}")),
    ("GitHub token (ghp_)", re.compile(r"\bghp_[A-Za-z0-9]{20,}")),
]


# ---------------------------------------------------------------- a small .gitignore reader (for use before git exists)
def _glob_to_re(pat):
    out, i = "", 0
    while i < len(pat):
        c = pat[i]
        if pat[i:i + 3] == "**/":
            out += "(?:.*/)?"; i += 3; continue
        if pat[i:i + 2] == "**":
            out += ".*"; i += 2; continue
        if c == "*": out += "[^/]*"
        elif c == "?": out += "[^/]"
        elif c == "[":
            j = pat.find("]", i + 1)
            if j == -1: out += re.escape(c)
            else: out += "[" + pat[i + 1:j].replace("\\", "\\\\") + "]"; i = j
        else: out += re.escape(c)
        i += 1
    return out


def load_ignore(root):
    rules = []
    p = os.path.join(root, ".gitignore")
    if not os.path.exists(p): return rules
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n").strip()
        if not line or line.startswith("#"): continue
        neg = line.startswith("!")
        if neg: line = line[1:]
        dir_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = "/" in line
        line = line.lstrip("/")
        body = _glob_to_re(line)
        rx = re.compile(("^" if anchored else "^(?:.*/)?") + body + "$")
        rules.append((rx, neg, dir_only))
    return rules


def ignored(rel, is_dir, rules):
    state = False
    for rx, neg, dir_only in rules:
        if dir_only and not is_dir: continue
        if rx.match(rel): state = not neg
    return state


def walk_files(root):
    rules = load_ignore(root)
    found = []
    for base, dirs, files in os.walk(root):
        rb = os.path.relpath(base, root).replace(os.sep, "/")
        rb = "" if rb == "." else rb
        keep = []
        for d in sorted(dirs):
            r = f"{rb}/{d}" if rb else d
            if d == ".git" or ignored(r, True, rules): continue
            keep.append(d)
        dirs[:] = keep
        for f in sorted(files):
            r = f"{rb}/{f}" if rb else f
            if not ignored(r, False, rules): found.append(r)
    return found


def git_files(root):
    """Files git would push, or None when this folder is not a git repo of its own."""
    if not os.path.isdir(os.path.join(root, ".git")): return None
    try:
        a = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
        b = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=AM", "-z"], cwd=root,
                           capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    names = {n for n in (a + b).decode("utf-8", "replace").split("\0") if n}
    return sorted(n for n in names if os.path.exists(os.path.join(root, n)))


def check(root=ROOT):
    files = git_files(root)
    mode = "git (tracked and staged files)"
    if files is None:
        files = walk_files(root)
        mode = "folder walk (git not started yet)"
    problems = []
    if mode.startswith("folder walk"):
        # ignored media would not be pushed, but one forced in with `git add -f` would be: flag it now
        listed = set(files)
        for base, dirs, names in os.walk(root):
            rb = os.path.relpath(base, root).replace(os.sep, "/")
            rb = "" if rb == "." else rb
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__") and not (not rb and d in ("brands", "output"))]
            for f in names:
                r = f"{rb}/{f}" if rb else f
                if os.path.splitext(f)[1].lower() in MEDIA and not r.startswith("example-brand/") and r not in listed:
                    problems.append((r, "image or video outside example-brand/ (ignored by .gitignore, but would be pushed if forced)"))
    for rel in files:
        full = os.path.join(root, rel)
        if not os.path.isfile(full): continue
        ext = os.path.splitext(rel)[1].lower()
        if ext in MEDIA and not rel.startswith("example-brand/"):
            problems.append((rel, "image or video outside example-brand/"))
        if rel.startswith("brands/") and rel != "brands/.gitkeep":
            problems.append((rel, "anything under brands/ must stay private"))
        if os.path.getsize(full) > MAX_BYTES and rel != FONT_OK:
            problems.append((rel, f"file is over 10MB ({os.path.getsize(full) // 1048576}MB)"))
        if ext in MEDIA or ext in (".ttf", ".otf", ".woff", ".woff2", ".zip", ".pyc"): continue
        try:
            with open(full, "rb") as f:
                data = f.read(2 * 1024 * 1024)
            if b"\0" in data: continue
            text = data.decode("utf-8", "replace")
        except OSError:
            continue
        for ln, line in enumerate(text.splitlines(), 1):
            for label, rx in PATTERNS:
                if rx.search(line):
                    problems.append((f"{rel}:{ln}", label))
    return mode, len(files), problems


def main():
    mode, n, problems = check()
    print(f"check_safe: looked at {n} files using {mode}")
    if problems:
        print("\nNOT SAFE TO PUSH:")
        for where, why in problems:
            print(f"  {where}  -  {why}")
        print("\nFix these (move private files out, delete the secret and change the key), then run this again.")
        sys.exit(1)
    print("OK: nothing private found.")


if __name__ == "__main__":
    main()
