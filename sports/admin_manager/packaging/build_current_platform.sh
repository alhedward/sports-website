#!/usr/bin/env bash
# Convenience wrapper for macOS/Linux. Windows uses build_windows.ps1.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "$(uname -s)" in
  Darwin) exec "$SCRIPT_DIR/build_macos.sh" ;;
  Linux) exec "$SCRIPT_DIR/build_linux.sh" ;;
  *) echo "Unsupported Unix platform. On Windows run packaging\\build_windows.ps1" >&2; exit 1 ;;
esac
