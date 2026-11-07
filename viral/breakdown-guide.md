# Breaking down the viral inbox

Goal: turn shares in `brands/NAME/viral/inbox/` into reusable angles in `brands/NAME/viral/angles.json`.

## Steps
1. Collect: `python3 viral/telegram_inbox.py --brand NAME --once`.
2. List folders in the inbox whose `message.json` has `"processed": false`.
3. For each one, read `message.json` (text, links) and look at the screenshots.
4. Write one entry per item in `angles.json` under `"angles"`:

```json
{
  "id": "short-kebab-id",
  "hook": "the hook line, in words you write yourself",
  "format": "list | story | non-negotiable | pov | other",
  "emotion": "the main feeling it creates",
  "slide_structure": [
    {"role": "hook", "note": "what the first slide does"},
    {"role": "point", "note": "what the middle slides do"},
    {"role": "close", "note": "what the last slide does"}
  ],
  "why_it_worked": "one or two honest sentences",
  "source_link": "the link from message.json",
  "source_inbox": "the inbox folder name",
  "status": "new"
}
```

5. Mark the inbox item processed: in its `message.json` set `"processed": true`, add `"processed_at"` (date) and `"angle_ids": ["short-kebab-id"]`.
6. To use an angle, write a post from the pattern with `"test": true` (see formats/test-angles.md), then set the angle's `status` to `"used"`.

## Rules
- Record the pattern, not the wording: write the hook in your own words.
- Never copy another creator's text or images into posts. Screenshots stay in the inbox as private notes; the inbox is never pushed.
- If an item has no clear pattern, still mark it processed, with an empty `angle_ids` and a one-line `"note"`.
