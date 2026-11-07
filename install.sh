#!/bin/sh
# Install drover as a personal Claude Code skill, or remove it with --uninstall.
# This script only writes SKILL.md and the drover helper. It never edits CLAUDE.md.
set -eu

src=$(cd "$(dirname "$0")" && pwd)/skills/drover
dest=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/drover

is_drover_skill() {
  grep -q '^name: drover$' "$1/SKILL.md" 2>/dev/null
}

case "${1:-}" in
  "") ;;
  --uninstall)
    if ! is_drover_skill "$dest"; then
      echo "No drover skill at $dest, nothing to remove."
      exit 0
    fi
    if [ -L "$dest" ]; then
      rm "$dest"
      echo "Removed the link at $dest. The files it pointed to are untouched."
      exit 0
    fi
    rm -f "$dest/SKILL.md" "$dest/drover"
    rmdir "$dest" 2>/dev/null || echo "Left $dest in place, it holds other files."
    echo "Removed drover from $dest. Subagent records and handoffs in ~/.claude/drover are untouched."
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
if [ -L "$dest" ]; then
  echo "$dest is a link to somewhere else, and copying would write through it. Remove the link first, nothing was changed." >&2
  exit 1
fi
if [ -e "$dest/SKILL.md" ] && ! is_drover_skill "$dest"; then
  echo "$dest holds a different skill. Move it first, nothing was changed." >&2
  exit 1
fi

mkdir -p "$dest"
cp "$src/SKILL.md" "$dest/SKILL.md"
cp "$src/drover" "$dest/drover"
chmod 755 "$dest/drover"
echo "Installed drover to $dest"

for tool in herdr claude python3 git; do
  command -v "$tool" >/dev/null 2>&1 || echo "Warning: $tool is not on your PATH, and drover needs it."
done
if command -v claude >/dev/null 2>&1 && claude plugin list 2>/dev/null | grep -q 'drover@'; then
  echo "Warning: the drover plugin is also installed. Keep one of the two, so Claude does not see two drover skills."
fi

cat <<'EOF'

Next steps:
  1. Restart Claude Code, or start a new session, inside a herdr pane.
  2. Run this there to check your setup:
EOF
echo "       $dest/drover doctor"
cat <<'EOF'

Optional: for a more reliable automatic trigger, add this line to your CLAUDE.md
yourself. This script did not change that file.

  When I ask for subagents or parallel agents and HERDR_ENV=1, use the drover skill so they run in visible herdr panes instead of the built-in Agent tool. This does not apply inside a drover pane (DROVER_CHILD=1).
EOF
