# Reactions Fallback Decision

## Status

- Decision status: `frozen`
- Based on:
  - [docs/spike_post_reactions.md](/d:/Projects/tg_post_analyzer/docs/spike_post_reactions.md)
  - [docs/spike_comment_reactions.md](/d:/Projects/tg_post_analyzer/docs/spike_comment_reactions.md)

## Spike-backed conclusions

- Post reactions retrieval is supported for at least one real channel post through the current Telethon/session setup.
- Comment reactions retrieval is supported for at least one real discussion thread through the current Telethon/session setup.
- For the tested discussion thread, both paths worked:
  - resolved `discussion_chat`
  - source entity with `reply_to=post.tg_message_id`
- Current spike evidence supports continuing with reactions persistence/collection work.

## Frozen fallback decision

### 1. Post reactions

- Post reactions are treated as `supported`.
- Downstream packages may implement post reactions collection/persistence without fallback downgrade by default.
- If a конкретный post fetch succeeds but `message.reactions` is absent, this must be treated as `no visible reactions`, not as a hard failure.

### 2. Comment reactions

- Comment reactions are treated as `supported but not globally guaranteed`.
- Default collection strategy should try the normal discussion-comments retrieval path first.
- If a concrete thread yields comment messages successfully but some or all comments have no `message.reactions`, this must be treated as `no visible reactions on sampled comments`, not as a crash condition.
- If a concrete thread cannot provide comment reactions because discussion resolution fails, entity path fails, or only one path works, downstream packages must preserve partial completion semantics rather than failing the whole refresh/report flow by default.

### 3. Partial/unsupported behavior contract

- Unsupported or partial comment reactions must degrade to `partial/incomplete reactions coverage`, not to job crash by default.
- Post-level data collection may still proceed when comment reactions are unavailable or partial.
- Comment text/comments count collection must remain usable even if comment reactions cannot be fetched for a thread.
- Report generation and downstream aggregation must be able to proceed with missing or partial comment reactions once those packages are implemented.

## Required downstream interpretation

- `posts.reactions`:
  - `supported`
  - absence of reactions on a fetched post means zero/none visible, not collector failure
- `comments.reactions`:
  - `best effort`
  - absence of reactions on fetched comments means zero/none visible on those comments
  - inability to fetch reactions for part of a thread means partial coverage
  - inability to resolve any usable comment-reaction path means unsupported for that thread instance, not proof of global platform unsupported status

## What is explicitly not frozen by this decision

- final persistence JSON schema
- exact payload fields for partial coverage metadata
- whether nested replies need the same completeness guarantees as top-level comments
- custom emoji reaction semantics
- UI wording for incomplete reactions coverage

## Blocker resolution

- Blocker B1: resolved for package planning purposes.
  - Reason: comment reactions capability is no longer unknown; support is confirmed on a real thread.
- Blocker B2: resolved at the fallback-policy level.
  - Reason: unsupported/partial comment reactions are now explicitly frozen as partial/incomplete coverage rather than hard failure by default.
