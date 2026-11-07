#!/usr/bin/env python3
"""Find faces in a brand's hook photos so the planner can keep text off them.

  python3 engine/detect_faces.py --brand NAME

Uses macOS Vision through a small Swift script. If swift or Vision is not available (Windows, Linux, no Xcode tools),
this prints a clear message and exits normally; the planner then falls back to its simple text placement.
Saves output/NAME/faces.json: id -> list of [x, y, w, h] as fractions of the (EXIF-oriented) image, top-left origin."""
import argparse, json, os, platform, shutil, subprocess, sys, time

import paths


def skip(msg):
    print("Face detection skipped: " + msg)
    print("That is fine. The planner will place text without checking faces and will say so in its report.")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="Detect faces in hook photos (macOS only).")
    ap.add_argument("--brand", required=True)
    a = ap.parse_args()
    paths.load_brand(a.brand)
    t0 = time.time()
    sel = paths.hooks_dir(a.brand)
    out = paths.faces_cache(a.brand)
    if platform.system() != "Darwin":
        skip("this needs macOS (Apple Vision).")
    if not shutil.which("swift"):
        skip("the 'swift' command was not found. Install Apple's command line tools with:  xcode-select --install")
    cache = paths.load_json(out, {}) or {}
    images = paths.list_images(sel)
    todo = [f for f in images if os.path.splitext(f)[0] not in cache]
    print(f"{len(cache)} cached, {len(todo)} to detect")
    if todo:
        try:
            p = subprocess.run(["swift", paths.swift_file()], input="\n".join(os.path.join(sel, f) for f in todo),
                               capture_output=True, text=True, timeout=1800)
        except (OSError, subprocess.TimeoutExpired) as ex:
            skip(f"could not run swift ({ex}).")
        if p.returncode != 0 or not p.stdout.strip():
            print((p.stderr or "")[-1500:])
            skip("swift or Vision failed to run on this computer.")
        try:
            res = json.loads(p.stdout)
        except ValueError:
            skip("swift gave an answer that could not be read.")
        for path, boxes in res["faces"].items():
            cache[os.path.splitext(os.path.basename(path))[0]] = [[round(v, 4) for v in b] for b in boxes]
        for path in res["failed"]:
            print("FAILED:", path)
        paths.save_json(out, cache, indent=None)
    n0 = sum(1 for v in cache.values() if not v)
    print(f"{len(cache)} images in cache, {n0} with no faces found, {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
