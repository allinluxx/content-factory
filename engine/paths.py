#!/usr/bin/env python3
"""The one place where every path in the project is worked out.

Nothing else in the project builds a path to a brand, a photo folder, the output folder, the font or the .env file.
Every command takes --brand NAME, which resolves to brands/NAME/ (or example-brand/ for the demo brand).
Output always goes to output/NAME/Batch N/.

CONTENT_FACTORY_ROOT (environment variable) can point the whole project at another folder; it exists so the tests
can run in a throwaway folder. Normally you never set it."""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.environ.get("CONTENT_FACTORY_ROOT")
                       or os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
EXAMPLE = "example-brand"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def check_name(name):
    if not name or not NAME_RE.match(name):
        die(f"'{name}' is not a usable brand name. Use letters, numbers, dashes and underscores only.")
    return name


# --------------------------------------------------------------------------- brand folders
def brand_dir(name):
    check_name(name)
    return os.path.join(ROOT, EXAMPLE) if name == EXAMPLE else os.path.join(ROOT, "brands", name)


def brand_exists(name):
    return os.path.isfile(brand_json(name))


def brand_json(name):
    return os.path.join(brand_dir(name), "brand.json")


def hooks_dir(name):
    return os.path.join(brand_dir(name), "photos", "hooks")


def hook_tags(name):
    return os.path.join(brand_dir(name), "photos", "hook_tags.json")


def product_dir(name):
    return os.path.join(brand_dir(name), "photos", "product")


def seen_hashes(name):
    return os.path.join(brand_dir(name), "photos", "seen_hashes.json")


def add_hooks_dir(name):
    return os.path.join(brand_dir(name), "add-photos", "hooks")


def add_product_dir(name):
    return os.path.join(brand_dir(name), "add-photos", "product")


def processed_dir(name):
    return os.path.join(brand_dir(name), "add-photos", "processed")


def inbox_dir(name):
    return os.path.join(brand_dir(name), "viral", "inbox")


def angles_json(name):
    return os.path.join(brand_dir(name), "viral", "angles.json")


def posts_file(name, batch):
    return os.path.join(brand_dir(name), "posts", f"batch{int(batch)}.json")


# --------------------------------------------------------------------------- output folders
def output_root(name):
    check_name(name)
    return os.path.join(ROOT, "output", name)


def batch_dir(name, batch):
    return os.path.join(output_root(name), f"Batch {int(batch)}")


def plan_file(name, batch):
    return os.path.join(batch_dir(name, batch), "_plan.json")


def report_file(name, batch):
    return os.path.join(batch_dir(name, batch), "Plan Report.md")


def library_dir(name):
    return os.path.join(output_root(name), "Photo Library")


def review_dir(name):
    return os.path.join(output_root(name), "Review Sheets")


def faces_cache(name):
    return os.path.join(output_root(name), "faces.json")


# --------------------------------------------------------------------------- project files
def font_path():
    return os.path.join(ROOT, "fonts", "TikTokSans-Variable.ttf")


def env_file():
    return os.path.join(ROOT, ".env")


def swift_file():
    return os.path.join(ROOT, "engine", "face_detect.swift")


def templates_dir():
    return os.path.join(ROOT, "engine", "templates")


def new_brand_dir(name):
    """Where new_brand.py creates a brand (never the example)."""
    check_name(name)
    if name == EXAMPLE:
        die(f"'{EXAMPLE}' is the built-in demo and cannot be created. Pick another name.")
    return os.path.join(ROOT, "brands", name)


# --------------------------------------------------------------------------- helpers
def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data, indent=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")


def list_images(folder):
    """Image files directly inside folder, sorted, ignoring hidden files."""
    if not os.path.isdir(folder):
        return []
    return sorted(n for n in os.listdir(folder)
                  if not n.startswith(".") and os.path.isfile(os.path.join(folder, n))
                  and os.path.splitext(n)[1].lower() in IMAGE_EXTS)


def rel(name, path):
    """Path relative to the brand folder, always with forward slashes."""
    return os.path.relpath(path, brand_dir(name)).replace(os.sep, "/")


def resolve_photo(name, relpath):
    """A photo path from a plan file -> full path. Refuses anything that leaves the brand folder."""
    if os.path.isabs(relpath) or ".." in relpath.replace("\\", "/").split("/"):
        die(f"unsafe photo path in plan: {relpath}")
    return os.path.join(brand_dir(name), *relpath.split("/"))


BRAND_DEFAULTS = {
    "brand": "", "product_type": "product", "audience": "", "voice": "", "proven_hooks": [], "never_say": [],
    "people_rules": "", "people_types": [], "sections": [], "tagsets": {}, "format_labels": {},
    "posting": {}, "settings": {}, "text": {},
}
POSTING_DEFAULTS = {"per_day": 3, "batch_size": 60, "start_date": "", "lead_with": [], "seasonal_families": [],
                    "seasonal_from": 0.4, "proven_first": 6}


def load_brand(name):
    """brand.json with defaults filled in. Stops with a plain message if the brand does not exist."""
    p = brand_json(name)
    if not os.path.exists(p):
        die(f"No brand called '{name}' (looked for {os.path.relpath(p, ROOT)}).\n"
            f"Make one with:  python3 engine/new_brand.py {name}")
    try:
        data = load_json(p)
    except ValueError as ex:
        die(f"{os.path.relpath(p, ROOT)} is not valid JSON: {ex}")
    b = dict(BRAND_DEFAULTS)
    b.update(data)
    b["posting"] = dict(POSTING_DEFAULTS, **(data.get("posting") or {}))
    return b


def section_folders(name, brand=None):
    """section key -> folder path, found by the NN-key folder names in photos/product/."""
    brand = brand or load_brand(name)
    root = product_dir(name)
    found = {}
    if os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            full = os.path.join(root, d)
            if os.path.isdir(full) and not d.startswith("."):
                found.setdefault(re.sub(r"^\d+[-_ ]*", "", d).lower(), full)
    out = {}
    for s in brand["sections"]:
        key = s["key"]
        if key.lower() in found:
            out[key] = found[key.lower()]
    return out
