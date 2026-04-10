# Comment Reactions Spike

## Goal

Verify whether the current Telethon/session setup can read reactions from discussion comments and whether the fetch path should go through the source entity or the resolved discussion chat.

## Scope

- Read-only exploratory spike
- Existing Telethon session only
- No schema/API/runtime changes

## Repro command

Run from repo root:

```bash
venv/Scripts/python.exe scripts/spike_comment_reactions.py --post-id 72 --limit 20
```

Windows `cmd.exe`:

```cmd
venv\Scripts\python.exe scripts\spike_comment_reactions.py --post-id 72 --limit 20
```

## Target used

- Local `posts.id`: `72`
- Channel: `@minsk_gl`
- Telegram message id: `14918`
- Local `comments_count`: `738`

## Result

- Status: `confirmed support`
- Notes:
  - Final successful run used the existing authorized Telethon session.
  - `GetDiscussionMessageRequest` resolved a discussion chat for the tested post.
  - Both retrieval paths returned top-level discussion comments:
    - `discussion_chat` scan
    - `source entity` scan via `reply_to=post.tg_message_id`
  - Both paths returned the same observed sample on this target.
  - Reactions were present on real discussion comments as `MessageReactions`.
  - Within the first 20 scanned top-level comments, 14 comments had visible reactions.

## Observed output summary

- Command:

```bash
venv/Scripts/python.exe scripts/spike_comment_reactions.py --post-id 72 --limit 20
```

- Outcome:
  - `status=ok`
  - `discussion_chat_id=1882768919`
  - `discussion_root_id=361493`
  - `discussion_scan.top_level_comments_scanned=20`
  - `discussion_scan.comments_with_reactions=14`
  - `source_scan.top_level_comments_scanned=20`
  - `source_scan.comments_with_reactions=14`
- Example reacted comments from the successful run:
  - comment `365456` -> `👎 x1`
  - comment `365452` -> `👎 x1`
  - comment `364783` -> `🔥 x1`

## Interpretation template

- Comment reactions retrieval is supported for at least one real discussion thread using the current Telethon client/session setup.
- This sample shows that top-level discussion comments can expose `message.reactions` as `MessageReactions`.
- On the tested target, `discussion_chat` and `source entity` paths both worked, so there is no evidence here that reactions require one exclusive entity path.
- This spike does not yet prove behavior for:
  - nested replies beyond the sampled top-level scan
  - threads with no discussion chat resolution
  - custom emoji reactions
  - every channel/discussion topology
