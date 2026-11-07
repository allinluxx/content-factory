#!/usr/bin/env python3
"""Turn a brand's posts file (brands/NAME/posts/batchN.json) into a renderable plan plus a plain-language report.

  python3 engine/plan_batch.py --brand example-brand --batch 1

Chooses hook photos (people / season / prefer rules, approved photos only, no repeats, text clear of faces),
photos for the later slides, family photos, the posting order, and checks that every text block fits.
It never edits the wording of the posts file (it only fills {placeholders} from brand.json settings).

Writes, inside output/NAME/Batch N/:  _plan.json (what render.py reads) and Plan Report.md (what you read)."""
import argparse, collections, json, math, os, re, sys, time

from PIL import Image

import paths
import render

W, H = render.W, render.H
CLEAN = 0.03            # fraction of a face that text may cover and still count as clean
MARGIN = 10             # px of air kept around text
W_PREFER, W_OVERLAP, W_DEMAND, W_RESERVED = 20.0, 25.0, 0.05, 40.0
BODY_PAGE = 0.68        # body text position on product-section photos
FAMILY_BODY_POS = (0.72, 0.8, 0.6)
FAMILY_TOP_FRAC = 0.22
LOW_RES_SIDE = 1000     # shortest side under this = low resolution, used only as a last resort
NODE_LIMIT = 60000     # backtracking budget for the posting order


# ----------------------------------------------------------------------------- geometry
def face_cover(faces, rects, w, h, top_bias):
    """Sum over faces of the fraction of the (visible) face that the text rects cover."""
    xo, yo, cw, ch = render.crop_box(w, h, top_bias)
    total = 0.0
    for fx, fy, fw, fh in faces:
        x0, x1 = (fx * w - xo) / cw * W, ((fx + fw) * w - xo) / cw * W
        y0, y1 = (fy * h - yo) / ch * H, ((fy + fh) * h - yo) / ch * H
        cx0, cx1, cy0, cy1 = max(x0, 0), min(x1, W), max(y0, 0), min(y1, H)
        if cx1 <= cx0 or cy1 <= cy0: continue
        area = (cx1 - cx0) * (cy1 - cy0)
        if area < 0.3 * (x1 - x0) * (y1 - y0): continue      # face mostly cropped away
        for (a, b, c, d) in rects:
            ix = min(cx1, c + MARGIN) - max(cx0, a - MARGIN)
            iy = min(cy1, d + MARGIN) - max(cy0, b - MARGIN)
            if ix > 0 and iy > 0: total += ix * iy / area
    return total


def face_in_top(faces, w, h, top_bias, frac=FAMILY_TOP_FRAC):
    xo, yo, cw, ch = render.crop_box(w, h, top_bias)
    for fx, fy, fw, fh in faces:
        y0, y1 = (fy * h - yo) / ch * H, ((fy + fh) * h - yo) / ch * H
        x0, x1 = (fx * w - xo) / cw * W, ((fx + fw) * w - xo) / cw * W
        if x1 > 0 and x0 < W and y1 > 0 and y0 < frac * H: return True
    return False


def rects_of(geoms):
    return [r for g in geoms.values() for r in g["line_rects"]]


# ----------------------------------------------------------------------------- hook slide templates
def hook_slide_variants(post, default_style):
    """List of (position_name, slide_dict_without_photo) the hook text can take."""
    box = post.get("hook_box")
    if box and len(box) >= 2:
        return [("split", {"heading": "", "text_style": "box", "text_top": box[0], "text_bottom": box[1]})]
    text = box[0] if box else post["hook"]
    style = {"text_style": "box"} if (box or default_style == "box") else {}
    return [(p, dict({"heading": text, "body": "", "position": p}, **style)) for p in ("top", "bottom", "middle")]


def best_hook_variant(post, h, faces_db, default_style):
    """(slide_without_photo, overlap, position) for the text position with least face coverage."""
    order = {"top": 0, "bottom": 1, "middle": 2, "split": 0}
    faces = faces_db.get(h["id"])
    best = None
    for name, tmpl in hook_slide_variants(post, default_style):
        slide = dict(tmpl, photo=h["rel"])
        if faces is None:                       # no face data: cannot tell, so take the first position
            cov = 0.0
        else:
            cov = face_cover(faces, rects_of(render.slide_geoms(slide)), h["width"], h["height"], True)
        key = (round(cov, 4), order[name])
        if best is None or key < best[0]: best = (key, slide, cov, name)
    return best[1], best[2], best[3]


# ----------------------------------------------------------------------------- hook photos
def image_size(path):
    """(width, height) as the photo is shown (EXIF rotation applied), without loading the pixels."""
    with Image.open(path) as im:
        w, h = im.size
        try:
            if im.getexif().get(274) in (5, 6, 7, 8): w, h = h, w
        except Exception:
            pass
    return w, h


def load_hooks(name, warnings):
    """Approved hook photos only. Returns (approved list, counts dict)."""
    tags = paths.load_json(paths.hook_tags(name), {}) or {}
    folder = paths.hooks_dir(name)
    files = {}
    for f in paths.list_images(folder):
        files.setdefault(os.path.splitext(f)[0], f)
    counts = {"approved": 0, "waiting": 0, "unlisted": 0, "missing": 0}
    hooks = []
    for hid in sorted(tags):
        t = tags[hid] or {}
        if t.get("status") != "approved":
            counts["waiting"] += 1
            continue
        if hid not in files:
            counts["missing"] += 1
            warnings.append(f"hook_tags.json says '{hid}' is approved but there is no image file with that name in photos/hooks/.")
            continue
        w, h = image_size(os.path.join(folder, files[hid]))
        people = [str(x).lower() for x in (t.get("people") or [])]
        hooks.append({"id": hid, "rel": "photos/hooks/" + files[hid], "width": w, "height": h,
                      "low_res": min(w, h) < LOW_RES_SIDE, "people": people,
                      "season": str(t.get("season") or "").lower(), "setting": t.get("setting") or "",
                      "mood": t.get("mood") or "", "activity": t.get("activity") or "",
                      "faces_visible": bool(t.get("faces_visible")),
                      "group": str(t.get("source_group") or hid)})
        counts["approved"] += 1
    counts["unlisted"] = sum(1 for k in files if k not in tags)
    return hooks, counts


def prefer_hits(h, prefer):
    hay = " ".join(str(h.get(k) or "") for k in ("activity", "mood", "setting")).lower()
    return sum(1 for w in prefer if w.lower() in hay)


def eligible(h, need, allow_low_res=False):
    people = set(h["people"])
    if not set(need.get("people", [])) <= people: return False
    if need.get("any") and not (set(need["any"]) & people): return False
    seasons = [s.lower() for s in need.get("season", [])]
    if seasons and h["season"] not in seasons: return False
    if h["low_res"] and not allow_low_res: return False
    if h["width"] / h["height"] > 1.1: return False                     # landscape photos crop badly
    hits = prefer_hits(h, need.get("prefer", []))
    if people and (not h["faces_visible"] or "sleeping" in h["activity"].lower()) and not hits: return False
    return True


# ----------------------------------------------------------------------------- posting order
class _GiveUp(Exception):
    pass


def order_posts(posts, cfg, warnings):
    """Posting order. Pins the lead posts first, holds seasonal families to the later part of the batch
    (posting.seasonal_from), then fills the rest by backtracking so that no family sits next to itself and no more than
    2 test posts fall in any 5. If the rules cannot all be met, relaxes them one at a time and says so in warnings."""
    n = len(posts)
    seq = [None] * (n + 2)                       # 1-based
    placed = set()
    lead = []
    for entry in cfg["lead_with"]:
        pool = [p for p in posts if p["id"] == entry and p["id"] not in placed]
        if not pool:
            fam = [p for p in posts if p["family"] == entry and p["id"] not in placed]
            pool = [p for p in fam if not p.get("test")] or fam
        if not pool:
            warnings.append(f"posting.lead_with names '{entry}' but no unplaced post has that id or family; skipped.")
            continue
        lead.append(pool[0]); placed.add(pool[0]["id"])
    for i, p in enumerate(lead, 1): seq[i] = p

    # seasonal posts, spread evenly over the later part of the batch
    sf = set(cfg["seasonal_families"])
    byfam = collections.OrderedDict()
    for p in posts:
        if p["family"] in sf and p["id"] not in placed: byfam.setdefault(p["family"], []).append(p)
    seasonal = []
    while any(byfam.values()):
        for fam in byfam:
            if byfam[fam]: seasonal.append(byfam[fam].pop(0))
    start = min(max(len(lead) + 1, int(cfg["seasonal_from"] * n) + 1), n)
    span = n - start + 1
    if len(seasonal) > span:
        warnings.append(f"{len(seasonal)} seasonal posts but only {span} places in the later part of the batch "
                        f"(from post {start}); some will sit earlier.")

    def clash(k, p):
        return any(0 < j <= n and seq[j] and seq[j]["family"] == p["family"] for j in (k - 1, k + 1))

    for i, p in enumerate(seasonal):
        target = start + int((i + 0.5) * span / len(seasonal)) if span >= len(seasonal) else start + i
        target = min(target, n)
        near = sorted(range(start, n + 1), key=lambda k: (abs(k - target), k))
        free = [k for k in near if seq[k] is None]
        spot = next((k for k in free if not clash(k, p)), None)
        if spot is None and free:
            spot = free[0]
            warnings.append(f"seasonal post '{p['id']}' had to sit next to a post of the same family (post {spot}).")
        if spot is None:
            continue                              # left for the general fill below
        seq[spot] = p; placed.add(p["id"])

    rest_all = [p for p in posts if p["id"] not in placed]
    n_tests = sum(1 for p in posts if p.get("test"))
    cap = min(int(cfg["proven_first"]), n - n_tests)
    idx = {p["id"]: i for i, p in enumerate(posts)}

    def solve(adjacency, window, proven):
        s = list(seq)
        free = [k for k in range(1, n + 1) if s[k] is None]
        nodes = [0]

        def tests_in(a, b):
            return sum(1 for j in range(a, b) if 1 <= j <= n and s[j] and s[j].get("test"))

        def ok(k, p):
            if adjacency:
                for j in (k - 1, k + 1):
                    if 1 <= j <= n and s[j] and s[j]["family"] == p["family"]: return False
            if proven and k <= cap and p.get("test"): return False
            return True

        def window_ok(k):
            if not window: return True
            for a in range(max(1, k - 4), k + 1):
                if tests_in(a, min(a + 5, n + 1)) > 2: return False
            return True

        def dfs(i, remaining):
            if i == len(free): return True
            nodes[0] += 1
            if nodes[0] > NODE_LIMIT: raise _GiveUp()
            k = free[i]
            left = collections.Counter(p["family"] for p in remaining)
            want_test = tests_in(1, k) < (n_tests / max(n, 1)) * k
            for p in sorted(remaining, key=lambda p: (-left[p["family"]], bool(p.get("test")) != want_test, idx[p["id"]])):
                if not ok(k, p): continue
                s[k] = p
                if window_ok(k) and dfs(i + 1, [q for q in remaining if q is not p]): return True
                s[k] = None
            return False

        try:
            return s[1:n + 1] if dfs(0, rest_all) else None
        except _GiveUp:
            return None

    attempts = [(True, True, True), (True, True, False), (False, True, True), (False, True, False),
                (True, False, False), (False, False, False)]
    for adjacency, window, proven in attempts:
        res = solve(adjacency, window, proven)
        if res is not None:
            gave_up = []
            if not adjacency: gave_up.append("same-family posts are not all kept apart")
            if not window: gave_up.append("more than 2 test posts fall in some run of 5")
            if not proven: gave_up.append(f"the first {cap} posts are not all proven")
            if gave_up:
                warnings.append("The posting order rules could not all be met, so: " + "; ".join(gave_up) +
                                ". Add more proven posts or fewer tests or families to fix this.")
            return res
    warnings.append("Could not order the posts; using the order in the posts file.")
    return list(posts)


# ----------------------------------------------------------------------------- input checks
def fill(text, settings):
    for k, v in settings.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def validate_posts(posts, section_keys, tagsets):
    errs = []
    seen = set()
    for i, p in enumerate(posts, 1):
        pid = p.get("id") or f"(post {i})"
        if not p.get("id"): errs.append(f"post {i}: missing id")
        elif p["id"] in seen: errs.append(f"{pid}: id used twice")
        seen.add(p.get("id"))
        for k in ("family", "title", "caption", "tags", "slides"):
            if not p.get(k): errs.append(f"{pid}: missing '{k}'")
        if not (p.get("hook") or p.get("hook_box")): errs.append(f"{pid}: needs 'hook' or 'hook_box'")
        if p.get("tags") and p["tags"] not in tagsets: errs.append(f"{pid}: tags '{p['tags']}' is not in brand.json tagsets")
        for n, s in enumerate(p.get("slides") or [], 1):
            if not (isinstance(s, list) and len(s) == 3):
                errs.append(f"{pid}: slide {n} must be [section, heading, body]"); continue
            if s[0] not in section_keys and s[0] not in ("family", "lifestyle"):
                errs.append(f"{pid}: slide {n} uses section '{s[0]}' which is not in brand.json sections "
                            f"(use one of {sorted(section_keys)}, 'family' or 'lifestyle')")
    return errs


# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    ap = argparse.ArgumentParser(description="Plan a batch: choose photos, order the posts, check the text fits.")
    ap.add_argument("--brand", required=True, help="brand name, e.g. example-brand")
    ap.add_argument("--batch", type=int, default=1, help="batch number (default 1)")
    a = ap.parse_args()
    name, batch = a.brand, a.batch
    brand = paths.load_brand(name)
    posting = brand["posting"]
    settings = brand["settings"]
    default_style = (brand.get("text") or {}).get("default_style", "outline")
    pf = paths.posts_file(name, batch)
    content = paths.load_json(pf)
    if content is None:
        paths.die(f"No posts file at {os.path.relpath(pf, paths.ROOT)}")
    raw_posts = content["posts"] if isinstance(content, dict) else content
    if not raw_posts:
        paths.die(f"{os.path.relpath(pf, paths.ROOT)} has no posts yet. Add some (see formats/ and AGENTS.md).")
    tagsets = dict(brand["tagsets"], **(content.get("tagsets", {}) if isinstance(content, dict) else {}))
    sections = paths.section_folders(name, brand)
    section_keys = [s["key"] for s in brand["sections"]]
    errs = validate_posts(raw_posts, section_keys, tagsets)
    if errs:
        paths.die("The posts file has problems:\n  - " + "\n  - ".join(errs))

    warnings = []
    hooks, counts = load_hooks(name, warnings)
    faces_db = paths.load_json(paths.faces_cache(name), {}) or {}
    if not faces_db:
        warnings.append("No face data (run engine/detect_faces.py, needs a Mac): the planner cannot check that text "
                        "stays off faces, so it takes the first text position and family photos are not face-checked.")

    # posts with {placeholders} filled in (wording is otherwise untouched)
    posts = []
    for p in raw_posts:
        q = json.loads(json.dumps(p))
        if "hook" in q: q["hook"] = fill(q["hook"], settings)
        if "hook_box" in q: q["hook_box"] = [fill(t, settings) for t in q["hook_box"]]
        q["slides"] = [[s[0], fill(s[1], settings), fill(s[2], settings)] for s in q["slides"]]
        q["title"], q["caption"] = fill(q["title"], settings), fill(q["caption"], settings)
        need = dict(q.get("need") or {})
        for k in ("people", "any", "season", "prefer"): need.setdefault(k, [])
        q["need"] = need
        posts.append(q)

    # photo seasons kept back for seasonal posts (a photo of that season is not spent on an ordinary post)
    sf = set(posting["seasonal_families"])
    reserved = {s.lower() for p in posts if p["family"] in sf for s in p["need"]["season"]}

    # ---- hook photos: hardest first
    assigned, used_ids, used_groups = {}, set(), set()
    low_res_used = []
    todo = list(posts)
    order_idx = {p["id"]: i for i, p in enumerate(posts)}

    def cands(p, allow_low=False):
        return [h for h in hooks if h["id"] not in used_ids and h["group"] not in used_groups
                and eligible(h, p["need"], allow_low)]

    def score(p, h, demand):
        slide, cov, pos = best_hook_variant(p, h, faces_db, default_style)
        s = W_PREFER * prefer_hits(h, p["need"].get("prefer", []))
        if cov >= CLEAN: s -= W_OVERLAP
        if h["season"] in reserved and not p["need"]["season"]: s -= W_RESERVED
        s -= W_DEMAND * demand
        return s, slide, cov, pos

    for allow_low in (False, True):
        while True:
            cmap = {p["id"]: cands(p, allow_low) for p in todo}
            ready = [p for p in todo if cmap[p["id"]]]
            if not ready: break
            p = min(ready, key=lambda p: (len(cmap[p["id"]]), order_idx[p["id"]]))
            demand = collections.Counter(h["id"] for q in todo if q is not p for h in cmap[q["id"]])
            best = max(((score(p, h, demand[h["id"]]), h) for h in cmap[p["id"]]), key=lambda t: t[0][0])
            (s, slide, cov, pos), h = best
            assigned[p["id"]] = {"h": h, "slide": slide, "cov": cov, "pos": pos, "cands": len(cmap[p["id"]])}
            used_ids.add(h["id"]); used_groups.add(h["group"])
            todo.remove(p)
            if allow_low: low_res_used.append((p["id"], h["id"]))
        if not todo: break
    dropped = []
    for p in todo:
        dropped.append(p["id"])
        warnings.append(f"NO HOOK PHOTO for post '{p['id']}' (need {json.dumps(p['need'])}); post dropped from the batch. "
                        f"Approve or add a matching photo in photos/hook_tags.json, then plan again.")
    for pid, i in low_res_used:
        warnings.append(f"LOW-RES hook photo {i} used as a last resort for '{pid}'.")
    posts = [p for p in posts if p["id"] in assigned]
    if not posts:
        paths.die("No post could be given a hook photo. Approved photos: "
                  f"{counts['approved']}. Tag photos in photos/hook_tags.json and set status to approved.")

    # ---- posting order
    ordered = order_posts(posts, posting, warnings)
    for i, p in enumerate(ordered, 1): p["number"] = i

    # ---- later slides
    section_photos = {}
    for key, folder in sections.items():
        section_photos[key] = [paths.rel(name, os.path.join(folder, f)) for f in paths.list_images(folder)]
    life_pool = section_photos.get("lifestyle")
    if not life_pool:
        life_pool = [x for k in section_keys for x in section_photos.get(k, [])]
    prod_use = collections.Counter()
    family_used = set()
    family_info = []
    dropped_late = []

    def product_pick(photos, in_post, pid, label):
        opts = sorted(photos, key=lambda x: (prod_use[x], photos.index(x)))
        free = [x for x in opts if x not in in_post]
        if not free:
            warnings.append(f"{pid}: {label} has only {len(photos)} photo(s), one repeats inside the post (unavoidable)")
            free = opts
        prod_use[free[0]] += 1
        return free[0]

    def family_pick(p, hook, text):
        """Choose a photo for a 'family' slide + body_position. Returns (hook-dict or None, body_pos, note)."""
        hp = set(hook["people"])
        has_text = bool(text[0].strip() or text[1].strip())
        for tier in (0, 1):                       # tier 1 lets a photo share a source group with one already used
            best = None
            for h in hooks:
                if h["id"] in used_ids or h["id"] in family_used: continue
                if tier == 0 and h["group"] in used_groups: continue
                if h["width"] / h["height"] > 1.1: continue
                if hp and (not h["faces_visible"] or not set(h["people"]) & hp): continue
                if h["season"] in reserved and not p["need"]["season"]: continue
                fc = faces_db.get(h["id"])
                bps = FAMILY_BODY_POS[:1]
                if has_text and fc is not None:
                    if face_in_top(fc, h["width"], h["height"], True): continue
                    bps = []
                    for bp in FAMILY_BODY_POS:
                        sl = {"photo": h["rel"], "heading": text[0], "body": text[1], "body_position": bp}
                        if face_cover(fc, rects_of(render.slide_geoms(sl)), h["width"], h["height"], True) < CLEAN:
                            bps = [bp]; break
                    if not bps: continue
                sc = (8 if set(h["people"]) == hp else 0) - (30 if h["low_res"] else 0) \
                    + (3 if h["group"] != hook["group"] else 0)
                if best is None or sc > best[0]: best = (sc, h, bps[0])
            if best:
                note = "low-res family photo" if best[1]["low_res"] else None
                if tier == 1: note = (note + "; " if note else "") + "shares a source group with another photo in the batch"
                return best[1], best[2], note
        # nothing with clear space: take the unused photo whose text covers least of a face, and say so
        best = None
        for h in hooks:
            if h["id"] in used_ids or h["id"] in family_used: continue
            if hp and not set(h["people"]) & hp: continue
            fc = faces_db.get(h["id"]) or []
            for bp in FAMILY_BODY_POS:
                sl = {"photo": h["rel"], "heading": text[0], "body": text[1], "body_position": bp}
                cov = face_cover(fc, rects_of(render.slide_geoms(sl)), h["width"], h["height"], True)
                if best is None or cov < best[0]: best = (cov, h, bp)
        if best:
            return best[1], best[2], f"no family photo with clear space; text may cover a face (cover {best[0]:.2f})"
        return None, FAMILY_BODY_POS[0], "no unused approved photo left"

    for p in sorted(ordered, key=lambda p: p["number"]):
        hook_h = assigned[p["id"]]["h"]
        slides = [dict(assigned[p["id"]]["slide"])]
        in_post = {hook_h["rel"]}
        bad = False
        for key, head, body in p["slides"]:
            sl = {"heading": head, "body": body}
            if default_style == "box": sl["text_style"] = "box"
            if key == "family":
                h, bp, issue = family_pick(p, hook_h, (head, body))
                if h is None:
                    warnings.append(f"{p['id']}: {issue} for a 'family' slide; post dropped from the batch.")
                    bad = True
                    break
                if issue: warnings.append(f"{p['id']}: {issue} ({h['id']})")
                family_used.add(h["id"]); used_ids.add(h["id"]); used_groups.add(h["group"])
                sl["photo"] = h["rel"]
                if body.strip(): sl["body_position"] = bp
                family_info.append((p["id"], h["id"], bp))
            elif key == "lifestyle":
                if not life_pool:
                    warnings.append(f"{p['id']}: 'lifestyle' slide but there are no product photos; post dropped.")
                    bad = True
                    break
                sl["photo"] = product_pick(life_pool, in_post, p["id"], "the lifestyle pool")
                if body.strip(): sl["body_position"] = BODY_PAGE
            else:
                photos = section_photos.get(key) or []
                if not photos:
                    warnings.append(f"{p['id']}: section '{key}' has no photos in photos/product/; post dropped.")
                    bad = True
                    break
                sl["photo"] = product_pick(photos, in_post, p["id"], f"section '{key}'")
                if body.strip(): sl["body_position"] = BODY_PAGE
            in_post.add(sl["photo"])
            slides.append(sl)
        if bad:
            dropped_late.append(p["id"])
            continue
        p["_slides"] = slides
    if dropped_late:
        ordered = [p for p in ordered if p["id"] not in dropped_late]
        for i, p in enumerate(ordered, 1): p["number"] = i
        dropped += dropped_late
    if not ordered:
        paths.die("Every post was dropped. See the warnings above.")

    # ---- fit checks
    fit_issues = []
    for p in ordered:
        for n, sl in enumerate(p["_slides"], 1):
            g = render.slide_geoms(sl)
            for bname, b in g.items():
                if b["size"] < b["nominal"]:
                    fit_issues.append(f"{p['number']:02d} {p['id']} slide {n} {bname}: text shrunk {b['nominal']}px -> {b['size']}px to fit")
                if b["y1"] > 0.97 * H:
                    fit_issues.append(f"{p['number']:02d} {p['id']} slide {n} {bname}: runs off the bottom (ends at {b['y1'] / H:.0%} of height)")
            if "heading" in g and "body" in g and g["heading"]["y1"] + 8 > g["body"]["y0"]:
                fit_issues.append(f"{p['number']:02d} {p['id']} slide {n}: heading and body overlap "
                                  f"(heading ends {g['heading']['y1']:.0f}px, body starts {g['body']['y0']:.0f}px)")
            if "text_top" in g and "text_bottom" in g and g["text_top"]["y1"] + 8 > g["text_bottom"]["y0"]:
                fit_issues.append(f"{p['number']:02d} {p['id']} slide {n}: top and bottom hook text overlap")

    # ---- words the brand never says
    for p in ordered:
        blob = " ".join([p.get("hook", ""), " ".join(p.get("hook_box", [])), p["title"], p["caption"]]
                        + [s[1] + " " + s[2] for s in p["slides"]]).lower()
        for phrase in brand["never_say"]:
            if phrase and phrase.lower() in blob:
                warnings.append(f"{p['id']}: contains a phrase from never_say: '{phrase}'")

    # ---- write plan json
    out_posts = []
    for p in sorted(ordered, key=lambda p: p["number"]):
        a_ = assigned[p["id"]]
        hook_text = " / ".join(p["hook_box"]) if p.get("hook_box") else p["hook"]
        out_posts.append({"number": p["number"], "id": p["id"], "family": p["family"], "test": bool(p.get("test")),
                          "type": "Test" if p.get("test") else "Proven", "need": p["need"], "hook_text": hook_text,
                          "hook_photo": a_["h"]["rel"], "title": p["title"], "caption": p["caption"],
                          "hashtags": tagsets[p["tags"]], "slides": p["_slides"]})
    plan_path = paths.plan_file(name, batch)
    paths.save_json(plan_path, {"brand": name, "batch": batch, "posts": out_posts, "settings": settings})

    # ---- checks on the result
    checks = []
    seq = out_posts
    n_in = len(raw_posts)
    checks.append((f"{len(seq)} of {n_in} posts planned", len(seq) == n_in))
    checks.append(("no family twice in a row", all(seq[i]["family"] != seq[i + 1]["family"] for i in range(len(seq) - 1))))
    n_proven = sum(1 for q in seq if not q["test"])
    cap = min(int(posting["proven_first"]), n_proven)
    leads = [q["id"] for q in seq[:len(posting["lead_with"])]]
    checks.append((f"first {cap} are proven (not test)", all(not q["test"] for q in seq[:cap])))
    if posting["lead_with"]:
        k = len(leads)
        opening = [(q["id"], q["family"]) for q in seq[:k]]
        ok_lead = all(any(w in pair for pair in opening) for w in posting["lead_with"]
                      if any(w in (q["id"], q["family"]) for q in seq))
        checks.append(("lead_with posts open the batch", ok_lead))
    checks.append(("max 2 test posts in any 5 in a row",
                   all(sum(q["test"] for q in seq[i:i + 5]) <= 2 for i in range(max(1, len(seq) - 4)))))
    if sf:
        pinned = set(leads)
        sp = [q["number"] for q in seq if q["family"] in sf and q["id"] not in pinned]
        lo = min(len(seq), int(posting["seasonal_from"] * len(seq)) + 1)
        checks.append((f"seasonal posts at positions {sp} (all from {lo} on)", all(x >= lo for x in sp)))
    all_lib = [s["photo"] for q in seq for s in q["slides"] if s["photo"].startswith(render.HOOK_PREFIX)]
    checks.append(("no hook-folder photo used twice in the batch", len(set(all_lib)) == len(all_lib)))
    by_rel = {h["rel"]: h for h in hooks}
    groups = [by_rel[x]["group"] for x in all_lib if x in by_rel]
    checks.append(("one photo per source group", len(set(groups)) == len(groups)))
    checks.append(("only approved photos used", all(x in by_rel for x in all_lib)))
    checks.append(("no photo repeated inside a post",
                   all(len({s["photo"] for s in q["slides"]}) == len(q["slides"]) for q in seq)))

    # ---- report
    L = []
    L.append(f"# {name} - batch {batch} plan report\n")
    L.append(f"Planned {len(out_posts)} posts from `{os.path.relpath(pf, paths.ROOT)}` in {time.time() - t0:.1f}s. "
             "Wording is untouched except `{placeholders}` filled from brand.json settings.\n")
    L.append("## Hook photos\n")
    L.append(f"- approved and usable: **{counts['approved']}**")
    L.append(f"- waiting (never used until approved): **{counts['waiting']}**")
    L.append(f"- image files not yet listed in hook_tags.json (also never used): **{counts['unlisted']}**\n")
    L.append("## Warnings\n")
    for w in warnings or ["none"]: L.append(f"- {w}")
    L.append("\n## Text fit (heading / body overflow)\n")
    for w in fit_issues or ["No overflow: every block fits at its nominal size and headings never touch the body text."]:
        L.append(f"- {w}")
    L.append("\n## Order checks\n")
    for cname, ok_ in checks: L.append(f"- {'PASS' if ok_ else 'FAIL'}: {cname}")
    L.append("\n## Posts\n")
    L.append("| # | Post | Family | Type | Hook photo | Text position | Candidates | Face cover | Hook people | Season |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for q in out_posts:
        a_ = assigned[q["id"]]; h = a_["h"]
        flag = "" if a_["cov"] < CLEAN else " OVERLAP"
        L.append(f"| {q['number']} | {q['id']} | {q['family']} | {q['type']} | {h['id']} | {a_['pos']} | {a_['cands']} | "
                 f"{a_['cov']:.2f}{flag} | {'+'.join(h['people']) or '-'} | {h['season'] or '-'} |")
    L.append("\n## Family slides\n")
    for pid, ph, bp in family_info: L.append(f"- {pid}: {ph}, body_position {bp}")
    if not family_info: L.append("- none")
    L.append("\n## Section photo usage\n")
    L.append("| Section | Photo use counts |\n|---|---|")
    for k, v in section_photos.items():
        L.append(f"| {k} | " + ", ".join(f"{os.path.basename(x)}: {prod_use[x]}" for x in v) + " |")
    if dropped:
        L.append("\n## Dropped posts\n")
        for d in dropped: L.append(f"- {d}")
    rep = paths.report_file(name, batch)
    with open(rep, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"wrote {os.path.relpath(plan_path, paths.ROOT)} and {os.path.relpath(rep, paths.ROOT)}")
    print(f"warnings: {len(warnings)}, fit issues: {len(fit_issues)}")
    for w in warnings: print("  WARNING: " + w)
    for cname, ok_ in checks: print(("PASS " if ok_ else "FAIL ") + cname)
    if not all(ok_ for _, ok_ in checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
