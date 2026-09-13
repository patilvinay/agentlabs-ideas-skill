#!/usr/bin/env bash
# Remove agentlabs-ideas-skill. Keeps the venv, your drafts and the panel
# unless --purge is given.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS="$HOME/.claude/hooks"; SETTINGS="$HOME/.claude/settings.json"
TMUXCONF="$HOME/.tmux.conf"; BINDIR="$HOME/.local/bin"; SKILLS="$HOME/.claude/skills"
VENV="${MD_VENV:-$HOME/.venvs/agentlabs-md}"
PURGE=0; [ "${1:-}" = "--purge" ] && PURGE=1
echo "==> tmux bindings"
[ -f "$TMUXCONF" ] && sed -i '/# >>> agentlabs-ideas >>>/,/# <<< agentlabs-ideas <<</d' "$TMUXCONF"
[ -n "${TMUX:-}" ] && tmux source-file "$TMUXCONF" 2>/dev/null || true
echo "==> hooks"
if [ -f "$SETTINGS" ] && command -v jq >/dev/null; then
  cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
  tmp=$(mktemp)
  jq --arg h "$HOOKS/" 'def strip: map(select([(.hooks//[])[].command]|any(startswith($h))|not));
    if .hooks then .hooks.Stop=((.hooks.Stop//[])|strip)
      | .hooks.Notification=((.hooks.Notification//[])|strip)
      | .hooks |= with_entries(select(.value|length>0)) else . end' "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
fi
for f in "$REPO"/hooks/*.sh "$REPO"/hooks/*.sh; do rm -f "$HOOKS/$(basename "$f")"; done
for f in "$REPO"/bin/*; do rm -f "$BINDIR/$(basename "$f")"; done
for d in "$REPO"/skills/*/; do [ -d "$d" ] && rm -rf "$SKILLS/$(basename "$d")"; done
rm -f "$HOME/.config/agentlabs/ideas-repo" "$HOME/.config/agentlabs/md-venv"
if [ "$PURGE" -eq 1 ]; then rm -rf "$VENV" "${AGENTLABS_SESSIONS:-$HOME/.claude/scratch}" "${AGENTLABS_VIEW:-$HOME/.claude/wave}"; echo "==> purged venv, scratch and panel"
else echo "    kept $VENV, your scratch dirs and the panel (--purge removes them)"; fi
echo "==> Done. Restart your agent."
