#!/usr/bin/env python3
"""Make contact sheets so a person (or an AI agent that can view images) can review photos and posts at a glance.

  python3 engine/review_sheets.py --brand NAME            sheets of every hook photo and product section
  python3 engine/review_sheets.py --brand NAME --batch 1  also one overview sheet for a planned batch

Sheets go to output/NAME/Review Sheets/. Each photo is labelled with its id, and hook photos show their status
(APPROVED or WAITING) so tagging can be checked by eye."""
import argparse, os

from PIL import Image, ImageDraw, ImageFont, ImageOps

import paths

COLS, ROWS = 6, 4
CELL_W, CELL_H = 200, 266
LABEL_H = 34
GAP = 10
BG = (30, 30, 30)


def label_font(size=15):
    try:
        return ImageFont.truetype(paths.font_path(), size)
    except OSError:
        return ImageFont.load_default()


def thumb(path):
    try:
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    except Exception:
        im = Image.new("RGB", (CELL_W, CELL_H), (80, 0, 0))
    return ImageOps.fit(im, (CELL_W, CELL_H), Image.LANCZOS, centering=(0.5, 0.2))


def sheet(items, out_prefix, title):
    """items: list of (image_path, label_line1, label_line2, colour). Writes one or more jpgs. Returns their paths."""
    if not items: return []
    per = COLS * ROWS
    font = label_font()
    written = []
    for page, start in enumerate(range(0, len(items), per), 1):
        chunk = items[start:start + per]
        rows = (len(chunk) + COLS - 1) // COLS
        sw = GAP + COLS * (CELL_W + GAP)
        sh = 40 + GAP + rows * (CELL_H + LABEL_H + GAP)
        im = Image.new("RGB", (sw, sh), BG)
        d = ImageDraw.Draw(im)
        d.text((GAP, 10), f"{title}  (page {page} of {(len(items) + per - 1) // per})", fill="white", font=label_font(18))
        for i, (path, l1, l2, colour) in enumerate(chunk):
            x = GAP + (i % COLS) * (CELL_W + GAP)
            y = 40 + GAP + (i // COLS) * (CELL_H + LABEL_H + GAP)
            im.paste(thumb(path), (x, y))
            d.text((x, y + CELL_H + 2), l1, fill="white", font=font)
            d.text((x, y + CELL_H + 18), l2, fill=colour, font=font)
        out = f"{out_prefix}-{page}.jpg" if len(items) > per else f"{out_prefix}.jpg"
        im.save(out, quality=88)
        written.append(out)
    return written


def main():
    ap = argparse.ArgumentParser(description="Contact sheets for reviewing photos and batches.")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--batch", type=int, default=None, help="also make an overview of this planned batch")
    a = ap.parse_args()
    name = a.brand
    brand = paths.load_brand(name)
    out = paths.review_dir(name)
    os.makedirs(out, exist_ok=True)
    for old in os.listdir(out):                          # only our own sheets
        if old.endswith(".jpg") and (old.startswith("hooks-") or old.startswith("product-") or old.startswith("batch-")):
            os.remove(os.path.join(out, old))
    made = []

    tags = paths.load_json(paths.hook_tags(name), {}) or {}
    hdir = paths.hooks_dir(name)
    approved, waiting = [], []
    for f in paths.list_images(hdir):
        hid = os.path.splitext(f)[0]
        t = tags.get(hid)
        who = "+".join(t.get("people") or []) if t else ""
        if t and t.get("status") == "approved":
            approved.append((os.path.join(hdir, f), hid, f"APPROVED {who} {t.get('season') or ''}".strip(), (120, 220, 120)))
        else:
            why = "WAITING" if t else "NOT TAGGED"
            waiting.append((os.path.join(hdir, f), hid, why, (240, 190, 80)))
    made += sheet(approved, os.path.join(out, "hooks-approved"), f"{name}: approved hook photos")
    made += sheet(waiting, os.path.join(out, "hooks-waiting"), f"{name}: hook photos waiting for your OK")

    folders = paths.section_folders(name, brand)
    for s in brand["sections"]:
        folder = folders.get(s["key"])
        if not folder: continue
        items = [(os.path.join(folder, f), f, s.get("label") or s["key"], (200, 200, 200)) for f in paths.list_images(folder)]
        made += sheet(items, os.path.join(out, f"product-{s['key']}"), f"{name}: section {s.get('label') or s['key']}")

    if a.batch is not None:
        plan = paths.load_json(paths.plan_file(name, a.batch))
        if plan is None:
            print(f"No plan for batch {a.batch} yet; run plan_batch.py first.")
        else:
            items = []
            for p in plan["posts"]:
                first = paths.resolve_photo(name, p["hook_photo"])
                items.append((first, f"{p['number']:02d} {p['id'][:22]}", p["type"] + " - " + p["family"],
                              (240, 190, 80) if p["test"] else (120, 220, 120)))
            made += sheet(items, os.path.join(out, f"batch-{a.batch}-overview"), f"{name}: batch {a.batch} hook photos in posting order")
    for m in made: print(os.path.relpath(m, paths.ROOT))
    print(f"{len(made)} sheet(s) in {os.path.relpath(out, paths.ROOT)}")


if __name__ == "__main__":
    main()
