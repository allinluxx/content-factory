# Content Factory

Turns your photos and your words into ready-to-post TikTok photo carousels (slides with text on top), in batches.
It ships with a made-up demo brand, **Sunny Sprouts**, so you can see it work before you add anything of your own.
You do not need to be a coder. You copy and paste a few commands.

## Quickest start: use Claude Code
If you have Claude Code, or another AI coding agent, you can skip the manual steps below. Paste this in:

> Clone https://github.com/allinluxx/content-factory into a new folder, read AGENTS.md, run the example brand to check it works, then interview me to set up my own brand.

You need access to this private repository first. The agent asks about your audience, voice and products, then helps you add your own photos. Your brand folder stays on your computer.

The manual steps below do the same job.

## What you need
- A Mac, Windows or Linux computer with **Python 3** (type `python3 --version` in a terminal; 3.9 or newer is fine).
  If it is missing, install it from https://www.python.org/downloads/
- Nothing else. The only extra piece is a picture library called Pillow, which step 1 installs for you.

## Step 1: open a terminal in this folder
- Mac: open the **Terminal** app, type `cd ` (with a space), drag this folder onto the window, press Return.
- Windows: open the folder, click the address bar, type `cmd`, press Enter.

## Step 2: set up (once)
```
sh setup.sh
```
(On Windows without `sh`, run `python -m pip install -r requirements.txt` instead.)

## Step 3: try the demo brand
Run these one at a time. Each one tells you what it did.
```
python3 engine/plan_batch.py --brand example-brand --batch 1
python3 engine/render.py --brand example-brand --batch 1
python3 engine/review_sheets.py --brand example-brand --batch 1
python3 engine/organise_photos.py --brand example-brand
```
Now open the new `output` folder:
- `output/example-brand/Batch 1/` has one numbered folder per post, in posting order. Each holds the slides (`slide-1.jpg` ...), `caption.txt` and a `preview.jpg`. `Post Order.csv` gives suggested dates. `Plan Report.md` is the planner explaining its choices and any warnings.
- `output/example-brand/Review Sheets/` has contact sheets for looking over photos quickly.
- `output/example-brand/Photo Library/` is your photos filed into folders. "Waiting For Your OK" holds photos that are not approved yet.

(The demo photos are plain coloured boards on purpose. Real photos go in your own brand.)

## Step 4: make your own brand
```
python3 engine/new_brand.py my-brand
```
This creates `brands/my-brand/`. Everything in `brands/` stays private on your computer; it is never pushed anywhere.
1. Open `brands/my-brand/brand.json` and fill it in: who you talk to, your voice, words you never say, your sections (the parts of your product you photograph), your hashtags.
2. Drop photos into `brands/my-brand/add-photos/hooks/` (photos for the first slide) and `brands/my-brand/add-photos/product/` (product photos, inside folders named like your sections, for example `02-inside`).
3. Run `python3 engine/add_photos.py --brand my-brand`.
4. New hook photos start as **waiting**. Nothing uses them until each one has its details filled in and is set to `"approved"` in `brands/my-brand/photos/hook_tags.json`. Look at `python3 engine/review_sheets.py --brand my-brand` first. Only approve photos of people who agreed to be used.
5. Write posts in `brands/my-brand/posts/batch1.json`. The files in `formats/` show each format and `formats/writing-guide.md` shows how to write. Easiest of all: ask an AI assistant to follow `AGENTS.md`.
6. Plan, render and review exactly as in step 3, replacing `example-brand` with `my-brand`.

Optional: on a Mac, `python3 engine/detect_faces.py --brand my-brand` finds faces so text can stay off them. On other computers it says so and the planner carries on without.

## Step 5 (optional): collect ideas from Telegram
1. In Telegram, message **@BotFather**, create a bot, copy the token.
2. Put the token and your chat id in `.env` (see the comments in `.env.example`).
3. Share posts you like to your bot, then run `python3 viral/telegram_inbox.py --brand my-brand --once`.
4. Ask your AI assistant to follow `viral/breakdown-guide.md`.
5. To check the inbox works without Telegram: `python3 viral/test_telegram_inbox.py`.

## Step 6: before you put this on GitHub
```
python3 engine/check_safe.py
```
It must say OK. It stops private photos, keys and personal folder paths from being pushed. Once the folder is a git repository, `sh setup.sh` switches it on automatically before every push.

## If something goes wrong
- "No brand called ...": check the name, or run `new_brand.py`.
- "NO HOOK PHOTO for post ...": no approved photo matches that post's `need`. Approve more photos or loosen the need.
- Anything else: the message says what to do. Ask your AI assistant to read `AGENTS.md` and help.
