#!/usr/bin/env bash
# Stop hook: push a <view>…</view> block to the panel the browser view shows.
#
# Mirrors the <voice> convention: <voice> is for the ear, <view> is for the
# panel. The reply on screen stays whatever it needs to be; the panel gets
# markdown authored for it — tables, checklists, diagrams worth keeping in sight.
#
# Same two races as speak-last.sh, so the same defence:
#   1. The hook can fire before the final message is flushed, which would push
#      a mid-turn preamble.
#   2. With nothing new, a naive "last entry" lookup re-pushes the previous turn.
# So: wait for the transcript to settle, then push only an unseen uuid.
#
# A reply with no <view> block leaves the panel alone — pushes are deliberate,
# and a stale-but-real view beats clobbering it with unrelated prose.
# Set CC_VIEW_FALLBACK=1 to mirror the whole reply (minus <voice>) instead.
#
# Images get rewritten before they reach Wave, because its preview block runs
# rehype-sanitize with the default schema and that schema is hostile in two
# specific ways:
#   * <svg> is not in tagNames, so inline vector markup is silently dropped.
#   * protocols.src is ["http","https"], so a data: URI loses its src, and
#     Wave's MarkdownImg then calls src.startsWith() on undefined and takes
#     the whole pane down with a TypeError.
# Both survive as ordinary files: resolveRemoteFile() joins a relative path
# against the md's own directory and streams it. So inline SVG and data URIs
# are written out as sibling asset-*.svg/png and referenced relatively.

# Everything agent-specific (where transcripts live, how a session is named)
# is in lib/agent.sh; nothing here names an agent.
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for _c in "$_here/../lib/agent.sh" "$HOME/.local/lib/agentlabs/agent.sh"; do
  [ -f "$_c" ] && { . "$_c"; break; }
done

view_dir="${AGENTLABS_VIEW:-$HOME/.claude/wave}"
view_md="$view_dir/claude-view.md"
state="$view_dir/.last-pushed.uuid"
settle="${CC_VIEW_SETTLE:-5}"

mkdir -p "$view_dir"

t=$(jq -r '.transcript_path // empty')
[ -n "$t" ] && [ -f "$t" ] || exit 0

prev=$(cat "$state" 2>/dev/null)

# Newest assistant entry carrying text, as "uuid<TAB>text" with the text JSON
# encoded so the whole message stays on one line.
newest() {
  jq -rs '[.[]
           | select(.type=="assistant")
           | select(any(.message.content[]?; .type=="text" and (.text|length)>0))]
          | last
          | "\(.uuid // "no-uuid")\t\(.message.content
              | map(select(.type=="text") | .text) | join("\n") | @json)"' "$t" 2>/dev/null
}

deadline=$(( $(date +%s) + settle ))
size=0; stable=0; row=""
while :; do
  now=$(stat -c %s "$t" 2>/dev/null || echo 0)
  [ "$now" = "$size" ] && stable=$((stable + 1)) || stable=0
  size=$now
  row=$(newest)
  uuid=${row%%$'\t'*}
  [ "$stable" -ge 3 ] && [ -n "$uuid" ] && [ "$uuid" != "$prev" ] && break
  [ "$(date +%s)" -ge "$deadline" ] && break
  sleep 0.2
done

uuid=${row%%$'\t'*}
[ -n "$uuid" ] && [ "$uuid" != "$prev" ] || exit 0

# Pull out <view>, or the whole reply minus <voice> when falling back, then
# externalise any inline SVG and data URIs. Python because the blocks span
# lines and this needs base64 and file writes anyway.
body=$(printf '%s' "${row#*$'\t'}" | \
  CC_VIEW_FALLBACK="${CC_VIEW_FALLBACK:-0}" CC_VIEW_DIR="$view_dir" python3 -c '
import base64, hashlib, json, os, pathlib, re, sys

text = json.loads(sys.stdin.read())
view_dir = pathlib.Path(os.environ["CC_VIEW_DIR"])

blocks = re.findall(r"(?ms)^<view>[ \t]*$(.*?)^</view>[ \t]*$", text)
if blocks:
    out = blocks[-1]
elif os.environ.get("CC_VIEW_FALLBACK") == "1":
    out = re.sub(r"<voice>.*?</voice>", "", text, flags=re.S)
else:
    sys.exit(0)

written = set()

def emit(data: bytes, ext: str) -> str:
    # Content-addressed, so an unchanged diagram keeps its filename and Wave
    # is not asked to re-fetch an identical asset every turn.
    name = f"asset-{hashlib.sha1(data).hexdigest()[:8]}.{ext}"
    (view_dir / name).write_bytes(data)
    written.add(name)
    return name

def inline_svg(mo):
    name = emit(mo.group(0).encode(), "svg")
    return f"![svg]({name})"

out = re.sub(r"<svg\b.*?</svg>", inline_svg, out, flags=re.S | re.I)

def data_uri(mo):
    alt, mime, b64 = mo.group(1), mo.group(2), mo.group(3)
    ext = {"svg+xml": "svg", "png": "png", "jpeg": "jpg",
           "gif": "gif", "webp": "webp"}.get(mime)
    if not ext:
        return f"`[unsupported data uri: {mime}]`"
    try:
        name = emit(base64.b64decode(b64), ext)
        return f"![{alt}]({name})"
    except Exception:
        return f"`[undecodable data uri]`"

out = re.sub(r"!\[([^\]]*)\]\(\s*data:image/([a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+?)\s*\)",
             data_uri, out)

# Anything still pointing at a data: URI would strip to src=undefined and crash
# the pane, so neutralise the leftovers rather than let them through.
out = re.sub(r"!\[([^\]]*)\]\(\s*data:[^)]*\)", r"`[dropped data uri: \1]`", out)

# Drop assets no longer referenced, so the directory tracks the current view.
for old in view_dir.glob("asset-*"):
    if old.name not in written:
        old.unlink(missing_ok=True)

sys.stdout.write(out.strip())
')

[ -n "$body" ] || exit 0

# Write through a temp file: the preview block must never read a half-written md.
tmp=$(mktemp "$view_dir/.push.XXXXXX")
{
  printf '%s\n' "$body"
  printf '\n---\n\n`%s`\n' "$(date '+%H:%M:%S')"
} > "$tmp"
mv -f "$tmp" "$view_md"
printf '%s' "$uuid" > "$state"
