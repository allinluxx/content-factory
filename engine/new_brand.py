#!/usr/bin/env python3
"""Make a blank brand folder from a template.

  python3 engine/new_brand.py my-brand [--product-type book|product|affiliate]

Creates brands/my-brand/ with brand.json to fill in, empty photo folders, add-photos folders, a viral inbox and an
empty posts/batch1.json. Never overwrites an existing brand. (brands/ is ignored by git, so your photos and
words stay on your computer.)"""
import argparse, os, re, shutil

import paths


def main():
    ap = argparse.ArgumentParser(description="Create a new, blank brand.")
    ap.add_argument("name", help="short name, letters/numbers/dashes, e.g. my-brand")
    ap.add_argument("--product-type", choices=["book", "product", "affiliate"], default="product")
    a = ap.parse_args()
    dest = paths.new_brand_dir(a.name)
    if os.path.exists(dest):
        paths.die(f"brands/{a.name} already exists; nothing changed.")
    t = paths.templates_dir()
    for d in ("photos/hooks", "photos/product", "add-photos/hooks", "add-photos/product", "viral/inbox", "posts"):
        os.makedirs(os.path.join(dest, d))
    brand = paths.load_json(os.path.join(t, "brand.json"))
    brand["product_type"] = a.product_type
    brand["brand"] = a.name.replace("-", " ").replace("_", " ").title()
    paths.save_json(os.path.join(dest, "brand.json"), brand, indent=2)
    shutil.copy(os.path.join(t, "hook_tags.json"), os.path.join(dest, "photos", "hook_tags.json"))
    shutil.copy(os.path.join(t, "batch1.json"), os.path.join(dest, "posts", "batch1.json"))
    shutil.copy(os.path.join(t, "angles.json"), os.path.join(dest, "viral", "angles.json"))
    for s in brand["sections"]:
        os.makedirs(os.path.join(dest, "photos", "product", f"{brand['sections'].index(s) + 1:02d}-{s['key']}"))
    key = re.sub(r"[^A-Za-z0-9]+", "_", a.name).upper()
    print(f"Created brands/{a.name}/")
    print("Next:")
    print(f"  1. Open brands/{a.name}/brand.json and fill it in (see AGENTS.md).")
    print(f"  2. Put photos in brands/{a.name}/add-photos/hooks/ and run:  python3 engine/add_photos.py --brand {a.name}")
    print(f"  3. For the Telegram inbox, add TELEGRAM_BOT_TOKEN_{key} and TELEGRAM_ALLOWED_CHAT_ID_{key} to .env")


if __name__ == "__main__":
    main()
