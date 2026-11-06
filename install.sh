#!/bin/sh
# Install herd as a personal Claude Code skill, or remove it with --uninstall.
# This script only writes SKILL.md and the herd helper. It never edits CLAUDE.md.
set -eu

src=$(cd "$(dirname "$0")" && pwd)/skills/herd
dest=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/herd

is_herd_skill() {
  grep -q '^name: herd$' "$1/SKILL.md" 2>/dev/null
}

case "${1:-}" in
  "") ;;
  --uninstall)
    if ! is_herd_skill "$dest"; then
      echo "No herd skill at $dest, nothing to remove."
      exit 0
    fi
    rm -f "$dest/SKILL.md" "$dest/herd"
    rmdir "$dest" 2>/dev/null || echo "Left $dest in place, it holds other files."
    echo "Removed herd from $dest. Subagent records and handoffs in ~/.claude/herd are untouched."
    exit 0
    ;;
  *)
    echo "usage: $0 [--uninstall]" >&2
    exit 2
    ;;
esac

if [ -e "$dest" ] && [ "$src" -ef "$dest" ]; then
  echo "$dest already points at this checkout, nothing to copy."
  exit 0
fi
if [ -e "$dest/SKILL.md" ] && ! is_herd_skill "$dest"; then
  echo "$dest holds a different skill. Move it first, nothing was changed." >&2
  exit 1
fi

mkdir -p "$dest"
cp "$src/SKILL.md" "$dest/SKILL.md"
cp "$src/herd" "$dest/herd"
chmod 755 "$dest/herd"
echo "Installed herd to $dest"

for tool in herdr claude python3 git; do
  command -v "$tool" >/dev/null 2>&1 || echo "Warning: $tool is not on your PATH, and herd needs it."
done
if command -v claude >/dev/null 2>&1 && claude plugin list 2>/dev/null | grep -q 'herd@'; then
  echo "Warning: the herd plugin is also installed. Keep one of the two, so Claude does not see two herd skills."
fi

cat <<'EOF'

Next steps:
  1. Restart Claude Code, or start a new session, inside a herdr pane.
  2. Run this there to check your setup:
EOF
echo "       $dest/herd doctor"
cat <<'EOF'

Optional: for a more reliable automatic trigger, add this line to your CLAUDE.md
yourself. This script did not change that file.

  When I ask for subagents or parallel agents and HERDR_ENV=1, use the herd skill so they run in visible herdr panes instead of the built-in Agent tool. This does not apply inside a herd pane (HERD_CHILD=1).
EOF
