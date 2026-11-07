#!/usr/bin/env python3
"""Rebuild output/NAME/Photo Library/ so you can browse a brand's photos in Finder or Explorer.

  python3 engine/organise_photos.py --brand NAME

Hook photos are filed by who is in them, then season. Product photos get one folder per section.
Anything not approved yet goes in "Waiting For Your OK". Files are hard-linked (copied if linking is not possible),
so no space is used. Safe to rerun: only the Photo Library folder itself is deleted and rebuilt, and only after a
check that it really is output/NAME/Photo Library. Your real photos are never touched."""
import argparse, os, shutil, sys

import paths

SEASONS = {"spring": "Spring", "summer": "Summer", "autumn": "Autumn", "fall": "Autumn", "winter": "Winter",
           "christmas": "Christmas", "": "Any Time", "any": "Any Time", "neutral": "Any Time"}


def who(people):
    p = sorted({str(x).strip().lower() for x in (people or []) if str(x).strip()})
    if not p: return "No People"
    names = [x.title() for x in p]
    return names[0] + " Only" if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def link(src, dest_dir, name, stats):
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest): return
    try:
        os.link(src, dest); stats["linked"] += 1
    except OSError:
        shutil.copy2(src, dest); stats["copied"] += 1


def safe_to_delete(out, brand):
    """The rebuild may only ever delete output/<brand>/Photo Library (not a link, not anywhere else)."""
    expected = os.path.realpath(paths.library_dir(brand))
    allowed_parent = os.path.realpath(os.path.join(paths.ROOT, "output", brand))
    return (os.path.basename(out) == "Photo Library" and os.path.realpath(os.path.dirname(out)) == allowed_parent
            and os.path.realpath(out) == expected and os.path.basename(os.path.dirname(allowed_parent)) == "output"
            and not os.path.islink(out))


def build(brand_name, quiet=False):
    brand = paths.load_brand(brand_name)
    out = paths.library_dir(brand_name)
    if os.path.lexists(out):
        if os.path.islink(out): paths.die("refusing: Photo Library is a symlink")
        if not safe_to_delete(out, brand_name): paths.die(f"refusing to delete {out}: not the expected Photo Library folder")
        shutil.rmtree(out)
    os.makedirs(out)
    stats = {"linked": 0, "copied": 0}

    # --- product photos, one folder per section ---
    folders = paths.section_folders(brand_name, brand)
    labels = {s["key"]: s.get("label") or s["key"] for s in brand["sections"]}
    placed_dirs = set()
    for i, s in enumerate(brand["sections"], 1):
        folder = folders.get(s["key"])
        if not folder: continue
        placed_dirs.add(os.path.realpath(folder))
        dest = os.path.join(out, "Product", f"{i:02d} {labels[s['key']]}")
        for f in paths.list_images(folder): link(os.path.join(folder, f), dest, f, stats)
    root = paths.product_dir(brand_name)
    if os.path.isdir(root):                      # product folders that match no section are waiting for a decision
        for d in sorted(os.listdir(root)):
            full = os.path.join(root, d)
            if os.path.isdir(full) and not d.startswith(".") and os.path.realpath(full) not in placed_dirs:
                for f in paths.list_images(full):
                    link(os.path.join(full, f), os.path.join(out, "Waiting For Your OK", "Product - " + d), f, stats)

    # --- hook photos ---
    tags = paths.load_json(paths.hook_tags(brand_name), {}) or {}
    hdir = paths.hooks_dir(brand_name)
    for f in paths.list_images(hdir):
        hid = os.path.splitext(f)[0]
        t = tags.get(hid)
        src = os.path.join(hdir, f)
        if t is None:
            dest = os.path.join(out, "Waiting For Your OK", "Not Yet Tagged")
        elif t.get("status") != "approved":
            dest = os.path.join(out, "Waiting For Your OK", "Tagged - Waiting")
        else:
            season = SEASONS.get(str(t.get("season") or "").lower(), str(t.get("season")).title())
            dest = os.path.join(out, "Hook Photos", who(t.get("people")), season)
        link(src, dest, f, stats)
    if not quiet:
        print(f"Photo Library built at {os.path.relpath(out, paths.ROOT)}: {stats['linked']} linked, {stats['copied']} copied")
    return stats


def main():
    ap = argparse.ArgumentParser(description="Rebuild the browsable Photo Library for a brand.")
    ap.add_argument("--brand", required=True)
    build(ap.parse_args().brand)


if __name__ == "__main__":
    main()
