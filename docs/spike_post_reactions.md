# Post Reactions Spike

## Goal

Verify whether the current Telethon/session setup can read reactions from a channel post without changing production code paths.

## Scope

- Read-only exploratory spike
- Existing Telethon session only
- No schema/API/runtime changes

## Repro command

Run from repo root:

```bash
venv/Scripts/python.exe scripts/spike_post_reactions.py --post-id 72
```

Windows `cmd.exe`:

```cmd
venv\Scripts\python.exe scripts\spike_post_reactions.py --post-id 72
```

## Target used

- Local `posts.id`: `72`
- Channel: `@minsk_gl`
- Telegram message id: `14918`
- Local `comments_count`: `738`

## Result

- Status: `confirmed support`
- Notes:
  - Local DB target exists and is reproducible.
  - Final successful run used the existing authorized Telethon session.
  - `message.reactions` was returned as `MessageReactions`.
  - The tested post exposed a populated `results` list with counts per emoji reaction.
  - The tested sample included standard emoji reactions only; custom emoji reactions were not observed on this target.

## Observed output summary

- Command:

```bash
venv/Scripts/python.exe scripts/spike_post_reactions.py --post-id 72
```

- Outcome:
  - `status=ok`
  - `entity_ref=minsk_gl`
  - `message_id=14918`
  - `reactions.supported=true`
  - `reactions.present=true`
  - `reactions.raw_type=MessageReactions`
- Example reaction rows from the successful run:
  - `❤`: `653`
  - `👍`: `321`
  - `😱`: `231`
  - `😭`: `95`
  - `🤣`: `80`

## Interpretation

- Post reactions retrieval is supported for at least one real channel post using the current Telethon client/session setup.
- Current production stack can read aggregate post reaction counts without schema or API changes.
- This spike does not yet prove anything about discussion comment reactions.
- This spike also does not yet prove custom emoji support, because the tested sample returned only standard emoji reactions.

## Expected evidence to record after run

- `message.reactions` is present with parsed `results`: post reactions retrieval is supported for the tested post.
- `message.reactions` is `null` but message fetch succeeds: retrieval path works, and the tested post simply has no visible reactions.
- Message fetch itself fails with a Telegram/API-specific error: record the exact failure as the spike result.
