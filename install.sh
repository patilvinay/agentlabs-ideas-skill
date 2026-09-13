#!/usr/bin/env bash
# agentlabs-ideas-skill installer. Safe to re-run: everything is idempotent.
#
#   ./install.sh              full install
#   ./install.sh --no-sudo    skip apt; only report what is missing
#   ./install.sh --no-skills  skip copying the skill into the agent's skills dir
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS="$HOME/.claude/hooks"; SETTINGS="$HOME/.claude/settings.json"
TMUXCONF="$HOME/.tmux.conf"; BINDIR="$HOME/.local/bin"
LIBDIR="$HOME/.local/lib/agentlabs"; SKILLS="$HOME/.claude/skills"
VENV="${MD_VENV:-$HOME/.venvs/agentlabs-md}"
MARK_BEGIN="# >>> agentlabs-ideas >>>"; MARK_END="# <<< agentlabs-ideas <<<"

USE_SUDO=1; WITH_SKILLS=1
for a in "$@"; do case "$a" in
  --no-sudo) USE_SUDO=0 ;;
  --no-skills) WITH_SKILLS=0 ;;
  -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $a" >&2; exit 2 ;;
esac; done
say(){ printf '\033[1m==>\033[0m %s\n' "$*"; }
warn(){ printf '\033[33m !\033[0m %s\n' "$*"; }
ok(){ printf '\033[32m  ok\033[0m %s\n' "$*"; }

PKGS=(tmux jq python3-venv curl wmctrl)
missing=(); for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if [ "${#missing[@]}" -eq 0 ]; then ok "system packages present"
elif [ "$USE_SUDO" -eq 1 ] && command -v apt-get >/dev/null 2>&1; then
  say "Installing: ${missing[*]}"; sudo apt-get update -qq && sudo apt-get install -y "${missing[@]}"
else warn "missing: ${missing[*]}"; warn "  sudo apt-get install -y ${missing[*]}"; fi

say "Python environment at $VENV"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet markdown-it-py mdit-py-plugins pygments linkify-it-py
ok "markdown-it-py, mdit-py-plugins, pygments, linkify-it-py"

say "Installing to $HOOKS, $BINDIR and $LIBDIR"
mkdir -p "$HOOKS" "$BINDIR" "$LIBDIR" "$HOME/.config/agentlabs"
install -m 0644 "$REPO"/lib/agent.sh "$LIBDIR"/agent.sh
install -m 0755 "$REPO"/hooks/*.sh "$HOOKS"/
install -m 0755 "$REPO"/bin/*      "$BINDIR"/
printf '%s\n' "$REPO" > "$HOME/.config/agentlabs/ideas-repo"
printf '%s\n' "$VENV" > "$HOME/.config/agentlabs/md-venv"
ok "$(ls "$REPO"/bin | wc -l) commands"
case ":$PATH:" in *":$BINDIR:"*) ok "$BINDIR is on PATH" ;;
  *) warn "$BINDIR is not on PATH. Add to ~/.bashrc or ~/.zshrc:"
     warn "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;; esac

if [ "$WITH_SKILLS" -eq 1 ] && [ -d "$REPO/skills" ]; then
  mkdir -p "$SKILLS"
  for d in "$REPO"/skills/*/; do n=$(basename "$d"); rm -rf "${SKILLS:?}/$n"; cp -r "$d" "$SKILLS/$n"; ok "skill: $n"; done
fi

if command -v jq >/dev/null 2>&1; then
  say "Registering the Stop hook in $SETTINGS"
  mkdir -p "$(dirname "$SETTINGS")"; [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
  cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
  tmp=$(mktemp)
  jq --arg view "$HOOKS/wave-view.sh" '
    def entry($c): {hooks:[{type:"command",command:$c,async:true,timeout:60}]};
    def strip($p): map(select([(.hooks//[])[].command] | any(. as $c | $p | index($c)) | not));
    .hooks = (.hooks // {})
    | .hooks.Stop = ((.hooks.Stop // []) | strip([$view])) + [entry($view)]
  ' "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
  ok "Stop hook registered (yours are left alone)"
else warn "jq not found — register hooks/wave-view.sh yourself, see the README"; fi

# ------------------------------------------------------------------ smoke test
# Render one page for real. A missing parser dependency only surfaces per
# request, so an install can otherwise look perfect and fail the first time you
# press the key -- which is exactly how linkify-it-py was missed once.
say "Checking the renderer"
_port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
"$BINDIR/md-server" --port "$_port" >/tmp/agentlabs-smoke.log 2>&1 &
_pid=$!
for _ in $(seq 40); do curl -sf "http://127.0.0.1:$_port/" >/dev/null 2>&1 && break; sleep 0.1; done
_probe=$(mktemp --suffix=.md); printf '# check\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nx = 1\n```\n' > "$_probe"
_sid=$(ls -1 "${AGENTLABS_SESSIONS:-$HOME/.claude/scratch}" 2>/dev/null | head -1)
if [ -n "$_sid" ]; then
  _code=$(curl -so /dev/null -w '%{http_code}' "http://127.0.0.1:$_port/s/$_sid" || echo 000)
else
  _code=$(curl -so /dev/null -w '%{http_code}' "http://127.0.0.1:$_port/" || echo 000)
fi
kill "$_pid" 2>/dev/null; rm -f "$_probe"
if [ "$_code" = 200 ]; then ok "renderer works (HTTP 200)"
else warn "renderer returned $_code — see /tmp/agentlabs-smoke.log"; fi

say "Adding key bindings to $TMUXCONF"
touch "$TMUXCONF"; sed -i "/$MARK_BEGIN/,/$MARK_END/d" "$TMUXCONF"
{ echo "$MARK_BEGIN"; echo "source-file $REPO/tmux/markdown.tmux.conf"; echo "$MARK_END"; } >> "$TMUXCONF"
ok "sourced from $REPO/tmux/markdown.tmux.conf"
[ -n "${TMUX:-}" ] && tmux source-file "$TMUXCONF" 2>/dev/null && ok "reloaded"
prefix=$(tmux show -gv prefix 2>/dev/null || true); prefix="${prefix:-C-b (tmux default)}"

cat <<TXT

$(printf '\033[1m==>\033[0m') Installed.

  Prefix is $prefix.  Press it, then:

    w   this session in the browser     W   tmux choose-tree

  Restart your agent so it picks up the Stop hook.
  Drafts:  sess new my-idea    then    sess review / approve / ship
TXT
