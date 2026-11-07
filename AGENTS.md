# AGENTS.md: operating instructions for any AI agent

This project makes TikTok photo carousels for any brand. It is brand neutral: everything specific to a brand lives in
`brands/NAME/` (private, git-ignored) or `example-brand/` (the public demo). Python 3.9, Pillow only, standard library otherwise.

## Golden rules
1. Always pass `--brand NAME`. Never hard-code a path; paths come from `engine/paths.py` only.
2. Never put brand material in the repo outside `example-brand/`. No photos of real people anywhere that git can see. `brands/*`, `output/`, `.env` are ignored; keep it that way.
3. Never use a photo that is not `"status": "approved"` in `photos/hook_tags.json`. Approval is a human decision about a person agreeing to be shown. Do not approve on your own; tag as `waiting`, show the review sheet, ask.
4. Do not invent anecdotes about real people or claims the brand cannot back. Follow `never_say` and `people_rules`. Affiliate or gifted posts must say so.
5. Do not run `git init`, push, or create remotes unless the human asks. Run `python3 engine/check_safe.py` before any push.

## Layout
- `engine/`: `paths.py`, `render.py`, `plan_batch.py`, `add_photos.py`, `organise_photos.py`, `detect_faces.py` (+ `face_detect.swift`), `review_sheets.py`, `new_brand.py`, `check_safe.py`, `make_example_images.py`, `templates/`.
- `formats/`: one file per post format, plus `writing-guide.md`. Read the format file before writing a post.
- `viral/`: `telegram_inbox.py`, `test_telegram_inbox.py`, `breakdown-guide.md`.
- `fonts/`: the slide font (OFL licence included). `.githooks/pre-push` runs `check_safe.py`.
- `output/NAME/`: generated, never committed: `Batch N/`, `Review Sheets/`, `Photo Library/`, `faces.json`.

## A brand (`brands/NAME/`)
```
brand.json
photos/hooks/            hook photos (first slide); id = file name without extension
photos/hook_tags.json    id -> {people[], season, setting, mood, activity, faces_visible, status, source_group?}
photos/product/NN-section/   product photos; every image in the folder is usable, no catalogue
add-photos/hooks/  add-photos/product/   drop zones for add_photos.py
viral/inbox/  viral/angles.json
posts/batch1.json  (batch2.json ...)
```
`brand.json`: `brand, product_type (book|product|affiliate), audience, voice, proven_hooks[], never_say[], people_rules, people_types[], sections[{key,label}], tagsets{}, format_labels{family->label}, posting{per_day,batch_size,start_date,lead_with[],seasonal_families[],seasonal_from,proven_first}, settings{} (text substitutions: {mum} in posts becomes settings.mum), text{default_style: outline|box}`.

## Posts file
```
{"posts": [{
  "id": "unique-id", "family": "nonneg", "test": false,
  "need": {"people": [...must all be present], "any": [...at least one], "season": [...allowed seasons], "prefer": [words matched in activity/mood/setting]},
  "hook": "text"   OR   "hook_box": ["top text", "bottom text"]  (white-box style),
  "slides": [["section-key" | "family" | "lifestyle", "heading", "body"], ...],
  "title": "emotional first line of the caption", "caption": "long caption", "tags": "tagset key"}]}
```
A slide with empty heading and body is a bare photo. `family` = another hook-folder photo of the same people. `lifestyle` = the section with key `lifestyle`, or any product photo if there is none.

## Workflows (replace NAME)
- New brand: `python3 engine/new_brand.py NAME`, fill `brand.json`.
- Add photos: drop files in `add-photos/`, run `python3 engine/add_photos.py --brand NAME`. Hook photos arrive as `waiting` with empty tags. Look at them (`engine/review_sheets.py --brand NAME`), fill in the tags, and only set `approved` once the human says so.
- Faces (Mac): `python3 engine/detect_faces.py --brand NAME`. If it says it was skipped, carry on; the report will say text was not face-checked.
- Write posts: pick formats from `formats/`, follow `formats/writing-guide.md`, save to `posts/batchN.json`. Proven formats are most of a batch; new angles carry `"test": true`.
- Plan: `python3 engine/plan_batch.py --brand NAME --batch N`. Read `output/NAME/Batch N/Plan Report.md`. Fix every WARNING and FAIL by changing photos, tags or needs, never by loosening the rules silently.
- Render: `python3 engine/render.py --brand NAME --batch N`, then look at several `preview.jpg` files to confirm text is readable and clear of faces.
- Review: `python3 engine/review_sheets.py --brand NAME --batch N`. Browse: `python3 engine/organise_photos.py --brand NAME`.
- Viral inbox: `python3 viral/telegram_inbox.py --brand NAME --once`, then follow `viral/breakdown-guide.md`.

## What the planner guarantees
One use per hook-folder photo in a batch; one per `source_group` (tag optional); hardest posts get photos first; needs are never relaxed silently (a post with no matching approved photo is dropped and listed as a warning); text kept off detected faces; same-family posts never adjacent; at most 2 test posts in any 5; the first `proven_first` slots (capped by how many proven posts exist) are proven; `lead_with` (post ids or families) opens the batch; `seasonal_families` posts are spread across the batch from the `seasonal_from` fraction and photos of their seasons are held back for them. Product-section photos are balanced by least use and not repeated inside a post when avoidable. If the ordering rules cannot all be met they are relaxed in steps and each relaxation is a warning.

Output: `output/NAME/Batch N/NN - Label - id/` (slide-N.jpg, caption.txt = title, blank, caption, blank, hashtags; metadata.json; preview.jpg), `Post Order.csv`, `Plan Report.md`.

## Rendering
Text style is fixed on purpose (do not change it): TikTok Sans, white outlined text or white-box text, 1080x1440. Emoji need Apple Color Emoji; elsewhere they are skipped with one warning.

## Safety checks
`python3 engine/check_safe.py` fails on images/videos outside `example-brand/`, files over 10MB (except the font), anything under `brands/` except `.gitkeep`, home-folder paths, and likely keys. The pre-push hook runs it. Never bypass the hook.
