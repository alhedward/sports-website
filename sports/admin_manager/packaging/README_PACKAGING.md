# Building the Sports.vk2ale Admin Manager desktop app

These scripts build a self-contained desktop bundle with PyInstaller. End users do **not** need to install Python, boto3, PyInstaller, or the app's Python dependencies. The build machine does need Python and internet access to install the build-time packages.

## Important platform rule

Build each target on its own operating system:

- Windows app: build on Windows
- Linux app: build on Linux
- macOS app: build on macOS

PyInstaller is not a cross-compiler, so a Linux box should not be used to produce the Windows or macOS deliverables.

## Folder layout

Run the scripts from the standalone admin-manager folder or from `sports/admin_manager` in the full repo. Expected files:

```text
sports_admin_manager.py
cognito_user_manager.py
requirements.txt
VERSION
packaging/
```

## Windows

From PowerShell:

```powershell
cd C:\path\to\sports-admin-manager
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\build_windows.ps1
```

Output:

```text
release\SportsAdminManager-windows-x64.zip
```

Users unzip it and run:

```text
SportsAdminManager.exe
```

## Linux

```bash
cd /path/to/sports-admin-manager
./packaging/build_linux.sh
```

Output:

```text
release/SportsAdminManager-linux-<arch>.tar.gz
```

Users extract it and run:

```bash
./SportsAdminManager/SportsAdminManager
```

For best compatibility, build on the oldest Linux distribution you want to support. PyInstaller bundles Python and Python packages, but Linux binaries still depend on normal base system libraries such as libc and the desktop/windowing stack.

## macOS

```bash
cd /path/to/sports-admin-manager
./packaging/build_macos.sh
```

Output:

```text
release/SportsAdminManager-macos-<arch>.dmg
```

Users open the DMG and copy `SportsAdminManager.app` to Applications.

The script ad-hoc signs the app for dev/private use. For wider distribution, sign with an Apple Developer ID Application certificate and notarize the DMG.

## Current-platform shortcut

On Linux/macOS:

```bash
./packaging/build_current_platform.sh
```

## Notes

- `boto3_direct` still needs AWS credentials on the user's machine because that mode intentionally talks directly to AWS. `cognito_api` mode does not need AWS credentials.
- Local app settings are still saved in `~/.sports-vk2ale-admin-manager.json`.
- Build outputs are intentionally not committed; keep `build/`, `dist/`, `.venv-build/`, and `release/` out of git unless you are attaching release artifacts.
