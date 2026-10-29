#!/usr/bin/env bash
# Install winddown to ~/.local/bin and add the Claude Code hook.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="${WINDDOWN_BIN:-$HOME/.local/bin}"
mkdir -p "$dest"
install -m 755 "$here/winddown.py" "$dest/winddown"
echo "Installed $dest/winddown"
case ":$PATH:" in
  *":$dest:"*) ;;
  *) echo "Add to your shell profile: export PATH=\"$dest:\$PATH\"" ;;
esac
PATH="$dest:$PATH" "$dest/winddown" install-hook
