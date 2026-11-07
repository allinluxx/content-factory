#!/usr/bin/env python3
"""Make the plain placeholder photos for example-brand (flat colour + a label, no people, no faces).

  python3 engine/make_example_images.py

Writes example-brand/photos/hooks/hook-001.jpg ... and example-brand/photos/product/NN-section/photo-00N.jpg,
and example-brand/photos/hook_tags.json if it does not exist yet. The images are already in the repo, so you only
need this to rebuild them. Each image is 1080 x 1440 and under 200KB."""
import colorsys, os

from PIL import Image, ImageDraw, ImageFont

import paths

W, H = 1080, 1440
NAME = paths.EXAMPLE

# id -> (people, season, setting, mood, activity, faces_visible, status, source_group)
HOOKS = [
    (["mum", "child"], "spring", "garden", "happy", "planting seeds", True, "approved", "visit-1"),
    (["mum", "child"], "spring", "kitchen", "playful", "mixing compost", True, "approved", "visit-1"),
    (["mum"], "summer", "garden", "calm", "watering", True, "approved", ""),
    (["dad", "child"], "summer", "garden", "happy", "watering", True, "approved", ""),
    (["dad"], "autumn", "porch", "calm", "reading the book", True, "approved", ""),
    (["child"], "spring", "garden", "curious", "looking at seedlings", True, "approved", ""),
    (["mum", "dad", "child"], "summer", "garden", "joyful", "digging together", True, "approved", ""),
    (["mum", "child"], "winter", "kitchen windowsill", "cosy", "planting seeds indoors", True, "approved", ""),
    (["dad", "child"], "winter", "living room", "cosy", "reading the book", True, "approved", ""),
    (["child"], "autumn", "garden", "proud", "harvesting carrots", True, "approved", ""),
    (["mum"], "autumn", "kitchen", "warm", "cooking the harvest", True, "approved", ""),
    (["mum", "child"], "any", "living room", "calm", "reading the book", True, "approved", ""),
    (["dad"], "spring", "garden", "focused", "building a raised bed", True, "approved", ""),
    (["child"], "summer", "patio", "happy", "watering", True, "approved", ""),
    (["mum", "dad"], "spring", "garden", "happy", "unboxing the kit", True, "waiting", ""),
    (None, None, None, None, None, None, "waiting", ""),                 # just added: not tagged yet
    (["mum", "child"], "summer", "garden", "happy", "picking strawberries", True, "waiting", ""),
    (None, None, None, None, None, None, "waiting", ""),                 # just added: not tagged yet
]
SECTIONS = [("01-kit", "The kit"), ("02-planting", "Planting"), ("03-bugs", "Bug hunt"),
            ("04-harvest", "Harvest"), ("05-story", "Story time")]


def font(size):
    try:
        f = ImageFont.truetype(paths.font_path(), size)
        f.set_variation_by_axes([14, 100, 600, 0])
        return f
    except (OSError, AttributeError):
        return ImageFont.load_default()


def make(path, hue, lines):
    r, g, b = colorsys.hsv_to_rgb(hue, 0.38, 0.62)
    im = Image.new("RGB", (W, H), (int(r * 255), int(g * 255), int(b * 255)))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, W - 40, H - 40], outline=(255, 255, 255), width=6)
    y = H // 2 - 40 * len(lines)
    for i, t in enumerate(lines):
        f = font(96 if i == 0 else 52)
        w = d.textlength(t, font=f)
        d.text(((W - w) / 2, y), t, font=f, fill=(255, 255, 255))
        y += 120 if i == 0 else 70
    d.text((W / 2 - 130, 58), "placeholder photo", font=font(36), fill=(240, 240, 240))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, quality=72, optimize=True)
    assert os.path.getsize(path) < 200 * 1024, path


def main():
    base = paths.brand_dir(NAME)
    tags = {}
    for i, (people, season, setting, mood, act, faces, status, group) in enumerate(HOOKS, 1):
        hid = f"hook-{i:03d}"
        label = [f"HOOK {i:02d}", (" + ".join(people) if people else "not tagged yet"), (season or "")]
        make(os.path.join(base, "photos", "hooks", hid + ".jpg"), (i * 0.137) % 1.0, [l for l in label if l])
        t = {"people": people or [], "season": season or "", "setting": setting or "", "mood": mood or "",
             "activity": act or "", "faces_visible": bool(faces), "status": status}
        if group: t["source_group"] = group
        tags[hid] = t
    for si, (folder, label) in enumerate(SECTIONS):
        for n in range(1, 4):
            make(os.path.join(base, "photos", "product", folder, f"photo-{n:03d}.jpg"), (si * 0.2 + n * 0.04 + 0.05) % 1.0,
                 [label.upper(), f"photo {n}"])
    tpath = paths.hook_tags(NAME)
    if not os.path.exists(tpath):
        paths.save_json(tpath, tags, indent=1)
    print(f"made {len(HOOKS)} hook photos and {len(SECTIONS) * 3} product photos in example-brand/photos/")


if __name__ == "__main__":
    main()
