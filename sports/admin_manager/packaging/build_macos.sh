#!/usr/bin/env bash
# Build Sports.vk2ale Admin Manager for macOS.
#
# Run this on macOS. The output .app includes Python and app dependencies.
# For private/dev use the script performs ad-hoc signing. For wider distribution,
# sign with a Developer ID Application certificate and notarize the DMG with Apple.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR"

APP_NAME="SportsAdminManager"
ARCH="$(uname -m)"
RELEASE_DIR="$APP_DIR/release"
VENV_DIR="$APP_DIR/.venv-build"

printf '==> Building %s for macOS %s from %s\n' "$APP_NAME" "$ARCH" "$APP_DIR"

rm -rf build dist
mkdir -p "$RELEASE_DIR"
python3 -m venv "$VENV_DIR"
PY="$VENV_DIR/bin/python"

"$PY" -m pip install --upgrade pip wheel
"$PY" -m pip install -r requirements.txt -r packaging/requirements-build.txt

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --add-data "VERSION:." \
  --collect-all boto3 \
  --collect-all botocore \
  --collect-all s3transfer \
  --collect-all jmespath \
  --collect-all dateutil \
  --collect-all urllib3 \
  sports_admin_manager.py

APP_BUNDLE="dist/$APP_NAME.app"
if command -v codesign >/dev/null 2>&1 && [[ -d "$APP_BUNDLE" ]]; then
  codesign --force --deep --sign - "$APP_BUNDLE" || true
fi

DMG="$RELEASE_DIR/$APP_NAME-macos-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG"

printf '\nBuilt macOS package: %s\n' "$DMG"
printf 'Users can open the DMG and copy SportsAdminManager.app to Applications.\n'
