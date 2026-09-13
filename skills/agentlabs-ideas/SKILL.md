---
name: agentlabs-ideas
description: Where to put design proposals, plans and drafts so the user can refine them — the per-session scratch/review/approved workflow and the <view> panel convention. Use when writing a design, plan, spec or anything the user will iterate on rather than read once, or when asked where a document should live.
---

# Session scratchpad

Long documents do not belong in a reply: they scroll away, cannot be edited,
and have to be copied by hand to become real. Each agent session has a
workspace instead.

    ~/.claude/scratch/<session-id>/
      00-scratch/    drafts — write here freely, nothing is final
      10-review/     the user is refining these
      20-approved/   signed off, ready to ship

## Rules

- Write only to `00-scratch/`. The other two stages are the user's; moving
  something into them is their decision, not yours.
- Name the file in your reply. Do not also paste its contents — that defeats
  the point.
- `session-dir` prints the directory for the current pane; `session-title`
  prints the session's display name.

## The user promotes it

    sess                    list this session's files by stage
    sess new NAME           create a draft
    sess review NAME        scratch  -> review
    sess approve NAME       review   -> approved
    sess ship NAME DIR      approved -> real docs

`prefix w` opens the session in a browser: the three stages in a sidebar,
with real SVG, mermaid and syntax-highlighted source.

## The `<view>` panel

A `<view>…</view>` block at the end of a reply is written to
`~/.claude/wave/claude-view.md` by the `wave-view.sh` Stop hook, and shown in the browser view. It is a different medium from both the reply and `<voice>`:

- `<voice>` is for the ear — plain prose, no markup.
- `<view>` is for the panel — tables, checklists, a diagram worth keeping in
  sight, a reference the next few turns will need.
- The reply on screen is neither.

Omit `<view>` for ordinary replies: a turn without one leaves the panel alone,
so pushes should be deliberate.

Fenced ```text blocks are passed through verbatim, which makes them the
reliable way to show an ASCII diagram — keep them under ~100 columns.
