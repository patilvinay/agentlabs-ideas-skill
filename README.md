# agentlabs-ideas-skill

A place to think, for terminal coding agents. Your agent drafts into a
per-session scratchpad; you refine it, approve it, and only then does it become
a real document. `prefix w` shows the session in your browser — rendered
markdown, mermaid, real SVG, syntax-highlighted source.

Nothing is published, nothing leaves the machine. The server binds `127.0.0.1`.

## Install

```bash
git clone https://github.com/patilvinay/agentlabs-ideas-skill && cd agentlabs-ideas-skill && ./install.sh
```

Then restart your agent so it picks up the Stop hook, and **run it**:

```bash
tmux            # then press  prefix w
```

That is the whole install — the browser server starts itself the first time you
press the key.

Flags: `--no-sudo` (report missing packages instead of installing them),
`--no-skills`.

## The workflow

```
~/.claude/scratch/<session-id>/
  00-scratch/    drafts — the agent writes here, nothing is final
  10-review/     you are refining these
  20-approved/   signed off, ready to ship
```

```bash
sess                    # list this session's files by stage
sess new NAME           # create a draft
sess review NAME        # scratch  → review
sess approve NAME       # review   → approved
sess ship NAME DIR      # approved → your real docs
```

Installing the skill is what teaches the agent to use it: drafts go to
`00-scratch/`, and it names the file rather than pasting a wall of markdown
into the reply.

## The browser view

`prefix w` opens `http://127.0.0.1:7677/s/<session-id>`.

One small server handles every session. The open page polls it, so pressing the
key again — or in a different session — moves that same tab instead of opening
another. With `wmctrl` present the window is raised too.

The sidebar carries the session's three stages, the `<view>` panel, the
markdown in the pane's working directory, and every tracked file of the git
repo around it. The repo listing comes from `git ls-files`, so ignored files
stay out — which is how secrets in an ignored config never appear.

| renders | how |
|---------|-----|
| markdown | markdown-it, GFM tables, anchors |
| code | pygments — in fences and whole source files |
| mermaid | client-side; needs network, degrades to the diagram source |
| SVG, images | served with their real content type, so SVG stays vector |
| PDF | embedded |

Every path is resolved and checked against an allowlist before being read: this
project's own directories, plus whatever working directory a pane reports.
Anything else is a 404.

## The `<view>` panel

A `<view>…</view>` block at the end of a reply is written to
`~/.claude/wave/claude-view.md` by the Stop hook and shown in the browser. It is
a different medium from the reply: tables, checklists, a diagram worth keeping
in sight. A reply without one leaves the panel alone.

## Agent support

| agent | status |
|-------|--------|
| **Claude Code** | implemented and tested |
| **Codex CLI** | adapter included, **not yet verified** — no Codex on the machine this was built on |

Everything agent-specific is in `lib/agent.sh`: where transcripts live and how
a session is named. Nothing else names an agent.

## Third-party services

One, and only for diagrams: **mermaid** is fetched from a CDN and rendered in
your browser. No document content is sent anywhere — the diagram source is
rendered locally by that script. Offline, diagrams show as their source and the
rest of the page is unaffected.

Nothing else talks to the network.

## Requirements

Linux, tmux ≥ 3.0, Python 3.10+, git. Built and tested on Ubuntu 24.04.
Package installation assumes `apt`; elsewhere the installer lists what is
missing. Raising the browser window uses `wmctrl`, which is X11 — under Wayland
the tab still updates, it just does not come to the front.

## Uninstall

```bash
./uninstall.sh            # keeps the venv, your drafts and the panel
./uninstall.sh --purge    # removes them too
```

Hooks are matched by path, so anything you added yourself is left alone.

## Companion

[agentlabs-voice](https://github.com/patilvinay/agentlabs-voice) — speech in and
out for the same agents, from the same tmux. Independent; installing both is
supported and they share one `lib/agent.sh`.

## Licence

MIT — see [LICENSE](LICENSE).
