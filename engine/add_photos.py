#!/usr/bin/env python3
"""Bring new photos into a brand.

  python3 engine/add_photos.py --brand NAME

Drop photos into:
  brands/NAME/add-photos/hooks/      -> become hook photos. They start as "waiting": nothing uses them until they are
                                        tagged and set to approved in photos/hook_tags.json.
  brands/NAME/add-photos/product/    -> product photos. Put them in a folder named like a section (e.g. 02-planting)
                                        and they join that section. Loose files go to photos/product/00-unsorted.

Photos are converted to JPEG (longest side 2000px), exact duplicates are skipped, originals move to add-photos/processed/."""
import argparse, hashlib, os, re, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone

from PIL import Image, ImageOps

import paths

EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
MAX_SIDE = 2000
EMPTY_TAGS = {"people": [], "season": "", "setting": "", "mood": "", "activity": "", "faces_visible": False,
              "status": "waiting"}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def to_jpeg(src, dest):
    ext = os.path.splitext(src)[1].lower()
    tmp = None
    try:
        if ext in (".heic", ".heif"):
            if not shutil.which("sips"):
                raise RuntimeError("HEIC photos need macOS (sips). Export them as JPEG first.")
            fd, tmp = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
            subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", tmp], check=True, capture_output=True)
            src = tmp
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "JPEG", quality=92)
        return im.size
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def photos_in(folder):
    if not os.path.isdir(folder): return []
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if not n.startswith(".") and os.path.isfile(os.path.join(folder, n))
                  and os.path.splitext(n)[1].lower() in EXTS)


def move_processed(name, src, sub, digest):
    d = os.path.join(paths.processed_dir(name), sub) if sub else paths.processed_dir(name)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, os.path.basename(src))
    if os.path.exists(dest):
        b, e = os.path.splitext(os.path.basename(src))
        dest = os.path.join(d, f"{b}_{digest[:8]}{e}")
    shutil.move(src, dest)


def next_number(folder, prefix):
    nums = []
    for n in os.listdir(folder) if os.path.isdir(folder) else []:
        m = re.match(rf"^{re.escape(prefix)}-(\d+)\.", n)
        if m: nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def main():
    ap = argparse.ArgumentParser(description="Add new photos to a brand.")
    ap.add_argument("--brand", required=True)
    name = ap.parse_args().brand
    brand = paths.load_brand(name)
    seen = paths.load_json(paths.seen_hashes(name), {}) or {}
    tags = paths.load_json(paths.hook_tags(name), {}) or {}
    hooks_out = paths.hooks_dir(name)
    added = dupes = failed = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def process(src, dest_for, kind, sub_processed):
        nonlocal added, dupes, failed
        try:
            digest = sha256(src)
            if digest in seen:
                dupes += 1
                move_processed(name, src, "Duplicates", digest)
                print(f"duplicate, skipped: {os.path.basename(src)}")
                return
            dest = dest_for()
            w, h = to_jpeg(src, dest)
            move_processed(name, src, sub_processed, digest)
            seen[digest] = {"file": paths.rel(name, dest), "kind": kind, "name": os.path.basename(src), "added": now}
            added += 1
            print(f"added {kind}: {os.path.basename(src)} -> {paths.rel(name, dest)}")
            return os.path.splitext(os.path.basename(dest))[0]
        except Exception as ex:
            failed += 1
            print(f"FAILED: {os.path.basename(src)}: {ex}", file=sys.stderr)

    for src in photos_in(paths.add_hooks_dir(name)):
        hid_holder = []
        def dest_for():
            n = next_number(hooks_out, "hook")
            hid = f"hook-{n:03d}"
            hid_holder.append(hid)
            return os.path.join(hooks_out, hid + ".jpg")
        if process(src, dest_for, "hook", ""):
            tags[hid_holder[-1]] = dict(EMPTY_TAGS)      # waiting, untagged: nothing uses it yet

    # product photos: files inside a section-named folder join that section, loose files go to 00-unsorted
    root = paths.add_product_dir(name)
    sections = paths.section_folders(name, brand)
    by_key = {k.lower(): v for k, v in sections.items()}
    targets = [(f, os.path.join(paths.product_dir(name), "00-unsorted")) for f in photos_in(root)]
    if os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            full = os.path.join(root, d)
            if not os.path.isdir(full) or d.startswith("."): continue
            key = re.sub(r"^\d+[-_ ]*", "", d).lower()
            dest_dir = by_key.get(key) or os.path.join(paths.product_dir(name), d)
            targets += [(f, dest_dir) for f in photos_in(full)]
    for src, dest_dir in targets:
        def dest_for(dest_dir=dest_dir):
            n = next_number(dest_dir, "photo")
            return os.path.join(dest_dir, f"photo-{n:03d}.jpg")
        process(src, dest_for, "product", "product")

    paths.save_json(paths.seen_hashes(name), seen)
    paths.save_json(paths.hook_tags(name), tags)
    print(f"Summary: {added} added, {dupes} duplicates skipped, {failed} failed")
    if added:
        print("New hook photos are WAITING. Tag them in photos/hook_tags.json and set status to approved to use them.")
    try:                                              # file new photos into the Photo Library
        import organise_photos
        organise_photos.build(name, quiet=True)
    except SystemExit:
        raise
    except Exception as ex:
        print(f"Photo Library update FAILED: {ex}", file=sys.stderr)
    if failed: sys.exit(1)


if __name__ == "__main__":
    main()
