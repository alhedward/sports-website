#!/usr/bin/env bash
# Build Sports.vk2ale Admin Manager for Linux.
#
# Run this on the oldest Linux distro you intend to support. PyInstaller bundles
# Python and Python packages, but Linux binaries still depend on the target
# system being broadly compatible with the build system libc/windowing stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR"

APP_NAME="SportsAdminManager"
ARCH="$(uname -m)"
RELEASE_DIR="$APP_DIR/release"
VENV_DIR="$APP_DIR/.venv-build"

printf '==> Building %s for Linux %s from %s\n' "$APP_NAME" "$ARCH" "$APP_DIR"

rm -rf build dist
mkdir -p "$RELEASE_DIR"
python3 -m venv "$VENV_DIR"
PY="$VENV_DIR/bin/python"

"$PY" -m pip install --upgrade pip wheel
"$PY" -m pip install -r requirements.txt -r packaging/requirements-build.txt

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
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

cat > "dist/$APP_NAME/$APP_NAME.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Sports Admin Manager
Comment=Sports.vk2ale local admin manager
Exec=$APP_NAME
Terminal=false
Categories=Utility;
DESKTOP

TARBALL="$RELEASE_DIR/$APP_NAME-linux-$ARCH.tar.gz"
rm -f "$TARBALL"
(
  cd dist
  tar -czf "$TARBALL" "$APP_NAME"
)

printf '\nBuilt Linux package: %s\n' "$TARBALL"
printf 'Users can extract it and run: ./SportsAdminManager/SportsAdminManager\n'
