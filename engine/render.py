#!/usr/bin/env python3
"""Render TikTok photo-mode slides (Classic-style text) from a planned batch.

  python3 engine/render.py --brand example-brand --batch 1

Reads output/NAME/Batch N/_plan.json (made by plan_batch.py) and writes the numbered post folders next to it."""
import argparse, csv, datetime, json, os, re, shutil, sys
from PIL import Image, ImageDraw, ImageFont, ImageOps

import paths

W, H = 1080, 1440
FONT_PATH = paths.font_path()
EMOJI_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"   # macOS only; elsewhere emoji are skipped with a warning
SS = 2  # text is drawn at 2x and downsampled for crisp edges
# variable font axes order: optical size, width, weight, slant
BOX_WGHT = 540                          # box style text is lighter than the outlined style
AXES = {"opsz": 14, "wdth": 92, "wght": 600, "slnt": 0}
HEAD_PX, BODY_PX = 62, 44
BOX_PX, BOX_SHORT_PX = 52, 60          # box style: normal / short single-block text
TRACK = -0.028                          # letter spacing, fraction of font size
SPACE_SCALE = 0.8                      # word space relative to font's space
STROKE_FRAC = 0.072                     # outline thickness as fraction of font size
LINE_SP = 1.16
MAX_W, MAX_BLOCK_H = 0.86 * W, 0.38 * H
BODY_CENTRE = 0.52
SETTINGS = {"canvas": [W, H], "heading_px": HEAD_PX, "body_px": BODY_PX, "box_px": BOX_PX,
            "box_short_px": BOX_SHORT_PX, "box_weight": BOX_WGHT, "font": "TikTokSans-Variable", "font_axes": AXES,
            "letter_spacing_em": TRACK, "space_scale": SPACE_SCALE, "stroke_em": STROKE_FRAC,
            "line_spacing": LINE_SP, "max_width": 0.86, "body_centre_default": BODY_CENTRE,
            "text_styles": ["outline (default)", "box"], "supersample": SS, "jpeg_quality": 92}
_emoji_font = None
_emoji_checked = False
_emoji_warned = False
_emoji_cache = {}
_font_cache = {}


def emoji_font():
    """The colour emoji font, or None when this computer does not have Apple Color Emoji."""
    global _emoji_font, _emoji_checked
    if not _emoji_checked:
        _emoji_checked = True
        try:
            _emoji_font = ImageFont.truetype(EMOJI_PATH, 160)
        except (OSError, IOError):
            _emoji_font = None
    return _emoji_font


def warn_no_emoji():
    global _emoji_warned
    if not _emoji_warned:
        _emoji_warned = True
        print("WARNING: Apple Color Emoji font not found on this computer, so emoji in slide text are skipped.",
              file=sys.stderr)


def get_font(size, wght=None):
    wght = wght or AXES["wght"]
    key = (int(round(size * SS)), wght)
    if key not in _font_cache:
        f = ImageFont.truetype(FONT_PATH, key[0])
        f.set_variation_by_axes([AXES["opsz"], AXES["wdth"], wght, AXES["slnt"]])
        _font_cache[key] = f
    return _font_cache[key]


def curly(t):
    t = re.sub(r'(^|[\s(\[{\u2014-])"', "\\1\u201c", t)
    t = t.replace('"', "\u201d")
    t = re.sub(r"(^|[\s(\[{\u2014-])'", "\\1\u2018", t)
    return t.replace("'", "\u2019")


HOOK_PREFIX = "photos/hooks/"


def is_hook_photo(photo):
    """Hook-folder photos are cropped from the top (faces sit high in the frame); product photos from the centre."""
    return photo.startswith(HOOK_PREFIX)


def load_photo(brand, photo):
    """photo is a path relative to the brand folder, e.g. photos/hooks/hook-001.jpg"""
    img = ImageOps.exif_transpose(Image.open(paths.resolve_photo(brand, photo)))
    return img.convert("RGB")


def fit(img, top_bias=False):
    return ImageOps.fit(img, (W, H), Image.LANCZOS, centering=(0.5, 0.1 if top_bias else 0.5))


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2190 <= o <= 0x2BFF or o in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x3030, 0x303D)


def tokenize(text):
    """Split into words; each word is a list of ('t', str) / ('e', char) segments."""
    words, cur, buf = [], [], ""
    def flush():
        nonlocal buf
        if buf: cur.append(("t", buf)); buf = ""
    for ch in text:
        o = ord(ch)
        if ch.isspace():
            flush()
            if cur: words.append(cur); cur = []
        elif o in (0xFE0F, 0xFE0E, 0x200D) or 0x1F3FB <= o <= 0x1F3FF:
            continue  # variation selectors, ZWJ, skin tones: drop (first glyph of cluster is kept)
        elif is_emoji(ch):
            if emoji_font() is None:
                warn_no_emoji()
                continue  # no emoji font on this computer: leave the emoji out
            flush(); cur.append(("e", ch))
        else:
            buf += ch
    flush()
    if cur: words.append(cur)
    return words


def emoji_img(ch, size):
    key = (ch, size)
    if key not in _emoji_cache:
        try:
            font = emoji_font()
            x0, y0, x1, y1 = font.getbbox(ch)
            im = Image.new("RGBA", (max(x1, 1) + 4, max(y1, 1) + 4), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((0, 0), ch, font=font, embedded_color=True)
            im = im.crop(im.getbbox() or (0, 0, 1, 1))
            _emoji_cache[key] = im.resize((size, size), Image.LANCZOS)
        except Exception:  # emoji font present but unusable: draw nothing for this glyph
            warn_no_emoji()
            _emoji_cache[key] = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return _emoji_cache[key]


def text_advances(txt, font, size):
    """x offset of each char (in 1x px) incl. kerning and tracking, plus total width."""
    xs = [font.getlength(txt[:i]) / SS + TRACK * size * i for i in range(len(txt))]
    return xs, font.getlength(txt) / SS + TRACK * size * len(txt)


def seg_width(seg, font, size):
    return size * 1.05 if seg[0] == "e" else text_advances(seg[1], font, size)[1]


def space_w(font, size):
    return font.getlength(" ") / SS * SPACE_SCALE


def layout_block(text, size, max_w=None, wght=None):
    """Wrap text; shrink font until block fits. Returns (lines, font, size, line_h)."""
    max_w = max_w or MAX_W
    words = tokenize(curly(text))
    while True:
        font = get_font(size, wght)
        space = space_w(font, size)
        lines, line, lw = [], [], 0
        for w in words:
            ww = sum(seg_width(s, font, size) for s in w)
            if line and lw + space + ww > max_w:
                lines.append(line); line, lw = [], 0
            lw += (space if line else 0) + ww
            line.append(w)
        if line: lines.append(line)
        lh = size * LINE_SP
        if len(lines) * lh <= MAX_BLOCK_H or size <= 20:
            return lines, font, size, lh
        size -= 2


def line_width(words, font, size):
    return sum(sum(seg_width(s, font, size) for s in w) for w in words) + space_w(font, size) * (len(words) - 1)


def draw_rich_line(layer, draw, words, font, size, cy, stroke, fill, stroke_fill, mode="fill"):
    """Draw one centred line on the 2x layer with its vertical box centred on cy (1x coords)."""
    space = space_w(font, size)
    x = (W - line_width(words, font, size)) / 2
    base = cy + size * 0.35
    for w in words:
        for seg in w:
            if seg[0] == "t":
                xs, tw = text_advances(seg[1], font, size)
                for ch, dx in zip(seg[1], xs):
                    if ch == " ": continue
                    if mode == "stroke":
                        draw.text(((x + dx) * SS, base * SS), ch, font=font, fill=stroke_fill,
                                  stroke_width=stroke * SS, stroke_fill=stroke_fill, anchor="ls")
                    else:
                        draw.text(((x + dx) * SS, base * SS), ch, font=font, fill=fill, anchor="ls")
                x += tw
            else:
                if mode == "fill":
                    e = emoji_img(seg[1], int(size * SS))
                    layer.paste(e, (int((x + size * 0.025) * SS), int((base - size * 0.85) * SS)), e)
                x += size * 1.05
        x += space


def box_pad(size):
    return size * 0.36, size * 0.1   # horizontal pad, extra vertical pad per side


def draw_boxes(draw, lines, font, size, y0, lh):
    """White rounded boxes hugging each line; adjoining lines touch/merge."""
    padx, _ = box_pad(size)
    rad = size * 0.28
    rects = []
    for i, ln in enumerate(lines):
        tw = line_width(ln, font, size)
        rects.append(((W - tw) / 2 - padx, y0 + i * lh, (W + tw) / 2 + padx, y0 + (i + 1) * lh))
    for i, (x0, t, x1, b) in enumerate(rects):
        prev = rects[i - 1] if i else None
        nxt = rects[i + 1] if i + 1 < len(rects) else None
        tl = not (prev and prev[0] <= x0 + rad)
        tr = not (prev and prev[2] >= x1 - rad)
        bl = not (nxt and nxt[0] <= x0 + rad)
        br = not (nxt and nxt[2] >= x1 - rad)
        # overlap 1px vertically so no hairline seam between boxes
        draw.rounded_rectangle([x0 * SS, t * SS, x1 * SS, (b + 1 if nxt else b) * SS], radius=rad * SS,
                               fill="white", corners=(tl, tr, br, bl))


def block_geom(text, size, style="outline", top=None, centre=None, bottom=None):
    """Layout of one text block without drawing: used by draw_block and by the planner (face / overflow checks).
    Returns None for empty text, else a dict with lines/font/size/lh, vertical extent y0..y1, per-line rects."""
    if not text.strip(): return None
    box = style == "box"
    lines, font, used, lh = layout_block(text, size, MAX_W if not box else 0.60 * W, BOX_WGHT if box else None)
    if box: lh = used * 1.13
    hgt = len(lines) * lh
    if bottom is not None: top = bottom - hgt
    y0 = top if top is not None else centre - hgt / 2
    padx = box_pad(used)[0] if box else used * STROKE_FRAC
    rects = []
    for i, ln in enumerate(lines):
        tw = line_width(ln, font, used)
        rects.append(((W - tw) / 2 - padx, y0 + i * lh, (W + tw) / 2 + padx, y0 + (i + 1) * lh))
    return {"lines": lines, "font": font, "size": used, "nominal": size, "lh": lh, "y0": y0, "y1": y0 + hgt,
            "line_rects": rects, "box": box}


def draw_block(canvas, text, size, style="outline", top=None, centre=None, bottom=None):
    g = block_geom(text, size, style, top, centre, bottom)
    if g is None: return
    box, lines, font, size, lh, y0 = g["box"], g["lines"], g["font"], g["size"], g["lh"], g["y0"]
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if box: draw_boxes(draw, lines, font, size, y0, lh)
    stroke = 0 if box else size * STROKE_FRAC
    fill, sfill = ("black", None) if box else ("white", "black")
    for mode in (("fill",) if box else ("stroke", "fill")):  # outlines first so glyphs never get overpainted
        for i, ln in enumerate(lines):
            draw_rich_line(layer, draw, ln, font, size, y0 + (i + 0.5) * lh, stroke, fill, sfill, mode)
    layer = layer.resize((W, H), Image.LANCZOS)
    canvas.paste(layer, (0, 0), layer)


TOP_Y, BOTTOM_Y, MIDDLE_Y = 0.09 * H, 0.91 * H, 0.45 * H


def slide_blocks(slide):
    """The text blocks render_slide draws for this slide: list of (name, text, size, style, kwargs)."""
    head, body = slide.get("heading", ""), slide.get("body", "")
    style = slide.get("text_style", "outline")
    bpos = slide.get("body_position")
    hsz = (BOX_SHORT_PX if len(head) <= 24 and not body.strip() else BOX_PX) if style == "box" else HEAD_PX
    bsz = BOX_PX if style == "box" else BODY_PX
    blocks = []
    tt, tb = slide.get("text_top", ""), slide.get("text_bottom", "")
    if tt.strip() or tb.strip():  # two-part hook: first string in the top area, second near the bottom
        sz = lambda t: BOX_SHORT_PX if len(t) <= 24 else BOX_PX
        blocks.append(("text_top", tt, sz(tt) if style == "box" else HEAD_PX, style, {"top": TOP_Y}))
        blocks.append(("text_bottom", tb, sz(tb) if style == "box" else HEAD_PX, style, {"bottom": BOTTOM_Y}))
    if body.strip():
        blocks.append(("heading", head, hsz, style, {"top": TOP_Y}))
        blocks.append(("body", body, bsz, style, {"centre": (bpos if bpos is not None else BODY_CENTRE) * H}))
    elif head.strip():
        pos = slide.get("position")
        kw = {"top": TOP_Y} if pos == "top" else {"bottom": BOTTOM_Y} if pos == "bottom" else {"centre": MIDDLE_Y}
        blocks.append(("heading", head, hsz, style, kw))
    return blocks


def slide_geoms(slide):
    """name -> block_geom for each text block of the slide (empty blocks skipped)."""
    out = {}
    for name, text, size, style, kw in slide_blocks(slide):
        g = block_geom(text, size, style, **kw)
        if g: out[name] = g
    return out


def crop_box(w, h, top_bias):
    """Source-pixel crop (x_off, y_off, crop_w, crop_h) that render.fit takes (mirrors ImageOps.fit)."""
    cx, cy = 0.5, (0.1 if top_bias else 0.5)
    if w / h >= W / H:
        cw, ch = round(h * W / H), h
        return (w - cw) * cx, 0, cw, ch
    cw, ch = w, round(w * H / W)
    return 0, (h - ch) * cy, cw, ch


def render_slide(slide, brand):
    canvas = fit(load_photo(brand, slide["photo"]), is_hook_photo(slide["photo"]))
    for name, text, size, style, kw in slide_blocks(slide):
        draw_block(canvas, text, size, style, **kw)
    return canvas


def contact_sheet(slides, path, th=480):
    tw = th * 3 // 4
    sheet = Image.new("RGB", (len(slides) * (tw + 10) + 10, th + 20), (30, 30, 30))
    for i, s in enumerate(slides):
        sheet.paste(s.resize((tw, th), Image.LANCZOS), (10 + i * (tw + 10), 10))
    sheet.save(path, quality=88)


def family_label(family, labels):
    return (labels or {}).get(family) or str(family or "Other").replace("-", " ").replace("_", " ").title()


def safe_part(text):
    return re.sub(r'[\\/:*?"<>|]+', "", str(text)).strip() or "post"


def render_post(post, brand, out_root, folder_name):
    folder = os.path.join(out_root, folder_name)
    os.makedirs(folder, exist_ok=True)
    slides = []
    for n, s in enumerate(post["slides"], 1):
        img = render_slide(s, brand)
        img.save(os.path.join(folder, f"slide-{n}.jpg"), quality=92)
        slides.append(img)
    tags = " ".join("#" + t.lstrip("#") for t in post.get("hashtags", []))
    with open(os.path.join(folder, "caption.txt"), "w", encoding="utf-8") as f:
        # title line, blank, caption, blank, hashtags
        f.write(post.get("title", "") + "\n\n" + post["caption"] + "\n\n" + tags + "\n")
    meta = dict(post, photo_sources=[s["photo"] for s in post["slides"]], render_settings=SETTINGS)
    with open(os.path.join(folder, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    contact_sheet(slides, os.path.join(folder, "preview.jpg"))
    return folder


def batch_folder_name(num, post, labels):
    return f"{num:02d} - {safe_part(family_label(post.get('family'), labels))} - {safe_part(post['id'])}"


def suggested_date(posting, batch, num):
    """Date a post is suggested for: start_date + whole days, per_day posts a day, batches follow on."""
    try:
        start = datetime.date.fromisoformat(str(posting.get("start_date") or ""))
    except ValueError:
        start = datetime.date.today()
    per_day = max(int(posting.get("per_day") or 3), 1)
    size = int(posting.get("batch_size") or 60)
    return start + datetime.timedelta(days=((batch - 1) * size + num - 1) // per_day)


def render_batch_folder(posts, brand, root, labels, posting, batch):
    """<root>/NN - Label - id/ per post, plus Post Order.csv. Old numbered post folders in root are replaced;
    anything else in root (the plan, the report) is left alone."""
    os.makedirs(root, exist_ok=True)
    for d in os.listdir(root):  # only our own generated post folders ("NN - Label - id"), never anything else
        p = os.path.join(root, d)
        if os.path.isdir(p) and re.match(r"^\d\d - .+ - .+$", d) and os.path.exists(os.path.join(p, "metadata.json")):
            shutil.rmtree(p)
    rows = []
    for i, p in enumerate(posts, 1):
        num = p.get("number", i)
        fname = batch_folder_name(num, p, labels)
        render_post(p, brand, root, fname)
        rows.append([f"{num:02d}", fname, "Test" if p.get("test") else "Proven", p.get("hook_text", ""),
                     p["slides"][0]["photo"], suggested_date(posting, batch, num).isoformat()])
        print(os.path.join(root, fname), flush=True)
    rows.sort(key=lambda r: r[0])
    with open(os.path.join(root, "Post Order.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["number", "folder", "type", "hook text", "hook photo", "suggested date"])
        w.writerows(rows)
    return root


def main():
    ap = argparse.ArgumentParser(description="Render a planned batch into slide images.")
    ap.add_argument("--brand", required=True, help="brand name, e.g. example-brand")
    ap.add_argument("--batch", type=int, default=1, help="batch number (default 1)")
    ap.add_argument("--plan", default=None, help="plan file to render (default: output/NAME/Batch N/_plan.json)")
    a = ap.parse_args()
    brand = paths.load_brand(a.brand)
    plan_path = a.plan or paths.plan_file(a.brand, a.batch)
    if not os.path.exists(plan_path):
        paths.die(f"No plan found at {plan_path}\nRun first:  python3 engine/plan_batch.py --brand {a.brand} --batch {a.batch}")
    plan = paths.load_json(plan_path)
    root = os.path.dirname(os.path.abspath(plan_path))
    render_batch_folder(plan["posts"], a.brand, root, brand["format_labels"], brand["posting"], a.batch)
    print(f"Rendered {len(plan['posts'])} posts into {root}")


if __name__ == "__main__":
    main()
