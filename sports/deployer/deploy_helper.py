#!/usr/bin/env python3
"""
LROC/SGARS/Sports Deployment Helper v1.15

Run:
  python3 deploy_helper.py

Install Tkinter if needed:
  sudo apt install python3-tk

Features:
- Select .tar.gz / .tgz / .zip packages.
- Latest... picker lists newest packages first.
- Extracts selected package to /tmp/site-deploy-...
- Finds lroc/, sgars/, or sports/ inside the package.
- Uses package-provided file.deploy.txt when available.
- Replaces placeholders including {{COMMIT_MESSAGE}}.
- Blocks unresolved placeholders.
- Uses rsync without --delete.
- Deploy modal streams command output live.
- Finished modal stays open for 30 seconds, then closes automatically.
- Selecting or pasting a package path automatically extracts and refreshes the script.
- Optionally watches GitHub Actions after git push using the GitHub CLI (`gh`).
- Compatible with older gh versions that do not support `gh run list --commit`.
- Shows verbose GitHub Actions job/step progress.
- Streams browser-style GitHub Actions job logs through the deploy modal when verbose output is enabled.
- Selecting a package from Latest... now opens the normal deploy confirmation prompt automatically.
- Latest... picker auto-refreshes when new packages appear in the selected folder.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import (
    BOTH, END, LEFT, RIGHT, TOP, BOTTOM, X, Y,
    BooleanVar, Button, Checkbutton, Entry, Frame, Label, Listbox, Scrollbar, StringVar,
    Text, Tk, Toplevel, filedialog, messagebox,
)
from tkinter import ttk


APP_TITLE = "LROC/SGARS/Sports Deployment Helper"
SUPPORTED_SUFFIXES = (".tar.gz", ".tgz", ".zip")
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
AEST = timezone(timedelta(hours=10), "AEST")
GITHUB_ACTIONS_APPEAR_TIMEOUT_SECONDS = 180
GITHUB_ACTIONS_WATCH_TIMEOUT_SECONDS = 45 * 60
GITHUB_ACTIONS_POLL_SECONDS = 5
MAX_FINAL_ACTION_LOG_CHARS = 120_000
MAX_LIVE_ACTION_LOG_CHARS_PER_POLL = 24_000


def strip_terminal_control(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines())


def aest_stamp() -> str:
    return datetime.now(AEST).strftime("%Y-%m-%d %H:%M:%S AEST")


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def default_download_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.exists() else Path.home()


def is_supported_package(path: Path) -> bool:
    return path.is_file() and any(str(path).endswith(suffix) for suffix in SUPPORTED_SUFFIXES)


def infer_commit_message(package_path: str, site_name: str) -> str:
    name = Path(package_path).name
    for suffix in (".tar.gz", ".tgz", ".zip"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    for prefix in (f"{site_name}-", f"{site_name}_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = re.sub(r"v\d+(?:\.\d+)+(?:-\d{4}-\d{2}-\d{2})?$", "", name)
    name = re.sub(r"\d{4}-\d{2}-\d{2}$", "", name)
    name = name.strip("-_ ")
    if not name:
        return f"Deploy {site_name.upper()} package"
    msg = " ".join(part for part in re.split(r"[-_]+", name) if part).strip()
    return (msg[:1].upper() + msg[1:]) if msg else f"Deploy {site_name.upper()} package"


def script_has_active_rsync_delete(script: str) -> bool:
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "--delete" in line:
            return True
    return False


DEFAULT_DEPLOY_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail

echo "== Deploying {site_name} from {package_path} =="
echo "Extracted source: {source_site_dir}"
echo "Destination:      {dest_site_dir}"

echo "== Copying {site_name} into repo =="
rsync -a \\
  --exclude '.terraform/' \\
  --exclude 'terraform.tfstate' \\
  --exclude 'terraform.tfstate.backup' \\
  "{source_site_dir}/" "{dest_site_dir}/"

cd "{dest_parent_dir}"

echo "== Validation =="
if [ -f "{site_name}/lambda/member_files.py" ]; then
  python3 -m py_compile "{site_name}/lambda/member_files.py"
fi
if [ -f "{site_name}/lambda/magazine_api.py" ]; then
  python3 -m py_compile "{site_name}/lambda/magazine_api.py"
fi
if [ -f "{site_name}/lambda/api/handler.py" ]; then
  python3 -m py_compile "{site_name}/lambda/api/handler.py"
fi
if [ -f "{site_name}/lambda/ingest/handler.py" ]; then
  python3 -m py_compile "{site_name}/lambda/ingest/handler.py"
fi
if [ -f "{site_name}/scripts/seed_data.py" ]; then
  python3 -m py_compile "{site_name}/scripts/seed_data.py"
fi
if [ -f "{site_name}/site/app.js" ]; then
  node --check "{site_name}/site/app.js"
fi
if [ -f "{site_name}/site/service-worker.js" ]; then
  node --check "{site_name}/site/service-worker.js"
fi
if [ -f "{site_name}/site/expo/expo.js" ]; then
  node --check "{site_name}/site/expo/expo.js"
fi
if [ -f "{site_name}/site/assets/vendor/amazon-chime-sdk-js-3.30.0.bundle.js" ]; then
  node --check "{site_name}/site/assets/vendor/amazon-chime-sdk-js-3.30.0.bundle.js"
fi
if command -v terraform >/dev/null 2>&1 && [ -d "{site_name}/terraform" ]; then
  echo "== Terraform fmt =="
  cd "{dest_parent_dir}/{site_name}/terraform"
  terraform fmt -recursive
  terraform init -backend=false
  terraform validate
  cd "{dest_parent_dir}"
fi

echo "== Git =="
git status
git add "{site_name}/VERSION" "{site_name}/lambda" "{site_name}/site" "{site_name}/terraform" "{site_name}/file.deploy.txt"
git status
git commit -m {commit_message_quoted}
git push
"""


SAMPLE_DEPLOY = """#!/usr/bin/env bash
set -euo pipefail

# Package deploy script. Place this as lroc/file.deploy.txt, sgars/file.deploy.txt, or sports/file.deploy.txt.
# deploy_helper.py replaces:
# {{PACKAGE_PATH}}
# {{EXTRACT_DIR}}
# {{SOURCE_SITE_DIR}}
# {{DEST_PARENT_DIR}}
# {{DEST_SITE_DIR}}
# {{SITE_NAME}}
# {{COMMIT_MESSAGE}}

echo "== Deploying {{SITE_NAME}} from {{PACKAGE_PATH}} =="
echo "Source: {{SOURCE_SITE_DIR}}"
echo "Dest:   {{DEST_SITE_DIR}}"

rsync -a \\
  --exclude '.terraform/' \\
  --exclude 'terraform.tfstate' \\
  --exclude 'terraform.tfstate.backup' \\
  "{{SOURCE_SITE_DIR}}/" "{{DEST_SITE_DIR}}/"

cd "{{DEST_PARENT_DIR}}"

echo "== Validation =="
if [ -f "{{SITE_NAME}}/lambda/member_files.py" ]; then
  python3 -m py_compile "{{SITE_NAME}}/lambda/member_files.py"
fi
if [ -f "{{SITE_NAME}}/lambda/magazine_api.py" ]; then
  python3 -m py_compile "{{SITE_NAME}}/lambda/magazine_api.py"
fi
if [ -f "{{SITE_NAME}}/lambda/api/handler.py" ]; then python3 -m py_compile "{{SITE_NAME}}/lambda/api/handler.py"; fi
if [ -f "{{SITE_NAME}}/lambda/ingest/handler.py" ]; then python3 -m py_compile "{{SITE_NAME}}/lambda/ingest/handler.py"; fi
if [ -f "{{SITE_NAME}}/scripts/seed_data.py" ]; then python3 -m py_compile "{{SITE_NAME}}/scripts/seed_data.py"; fi
node --check "{{SITE_NAME}}/site/app.js"
node --check "{{SITE_NAME}}/site/service-worker.js"
if [ -f "{{SITE_NAME}}/site/expo/expo.js" ]; then node --check "{{SITE_NAME}}/site/expo/expo.js"; fi
if [ -f "{{SITE_NAME}}/site/assets/vendor/amazon-chime-sdk-js-3.30.0.bundle.js" ]; then node --check "{{SITE_NAME}}/site/assets/vendor/amazon-chime-sdk-js-3.30.0.bundle.js"; fi
if command -v terraform >/dev/null 2>&1 && [ -d "{{SITE_NAME}}/terraform" ]; then cd "{{DEST_PARENT_DIR}}/{{SITE_NAME}}/terraform" && terraform fmt -recursive && terraform init -backend=false && terraform validate && cd "{{DEST_PARENT_DIR}}"; fi

git status
git add "{{SITE_NAME}}/VERSION" "{{SITE_NAME}}/lambda" "{{SITE_NAME}}/site" "{{SITE_NAME}}/terraform" "{{SITE_NAME}}/file.deploy.txt"
git status
git commit -m "{{COMMIT_MESSAGE}}"
git push
"""


def replace_placeholders(script: str, values: dict[str, str]) -> str:
    replacements = {
        "{{PACKAGE_PATH}}": values.get("package_path", ""),
        "{{EXTRACT_DIR}}": values.get("extract_dir", ""),
        "{{SOURCE_SITE_DIR}}": values.get("source_site_dir", ""),
        "{{DEST_PARENT_DIR}}": values.get("dest_parent_dir", ""),
        "{{DEST_SITE_DIR}}": values.get("dest_site_dir", ""),
        "{{SITE_NAME}}": values.get("site_name", ""),
        "{{COMMIT_MESSAGE}}": values.get("commit_message", ""),
    }
    for key, val in replacements.items():
        script = script.replace(key, val)

    for generic in (
        f"Deploy {values.get('site_name','')} package",
        f"Deploy {values.get('site_name','').upper()} package",
        "Deploy LROC Package",
        "Deploy lroc package",
        "Deploy SGARS Package",
        "Deploy sgars package",
        "Deploy SPORTS Package",
        "Deploy sports package",
    ):
        script = script.replace(f'git commit -m "{generic}"', "git commit -m " + shell_quote(values["commit_message"]))
        script = script.replace(f"git commit -m '{generic}'", "git commit -m " + shell_quote(values["commit_message"]))

    script = script.replace("rsync -a --delete", "rsync -a")
    script = script.replace("  --delete \\\n", "")
    return script


class LatestPackageBrowser:
    def __init__(self, parent: Tk, start_dir: Path, on_select) -> None:
        self.on_select = on_select
        self.current_dir = StringVar(value=str(start_dir))
        self.filter_text = StringVar(value="")
        self.files: list[Path] = []
        self._last_scan_signature: tuple[tuple[str, int, int], ...] = tuple()
        self._auto_refresh_ms = 2000

        self.window = Toplevel(parent)
        self.window.title("Select latest package")
        self.window.geometry("920x560")
        self.window.transient(parent)

        top = Frame(self.window, padx=10, pady=8)
        top.pack(side=TOP, fill=X)
        Label(top, text="Folder").grid(row=0, column=0, sticky="w")
        Entry(top, textvariable=self.current_dir, width=78).grid(row=0, column=1, sticky="ew", padx=6)
        Button(top, text="Browse…", command=self.choose_folder).grid(row=0, column=2)

        Label(top, text="Filter").grid(row=1, column=0, sticky="w")
        filt = Entry(top, textvariable=self.filter_text)
        filt.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        filt.bind("<KeyRelease>", lambda _e: self.refresh())
        Button(top, text="Refresh", command=self.refresh).grid(row=1, column=2, pady=(6, 0))
        top.columnconfigure(1, weight=1)

        body = Frame(self.window, padx=10)
        body.pack(side=TOP, fill=BOTH, expand=True)
        self.tree = ttk.Treeview(body, columns=("modified", "size", "name"), show="headings")
        self.tree.heading("modified", text="Modified")
        self.tree.heading("size", text="Size")
        self.tree.heading("name", text="Package")
        self.tree.column("modified", width=155)
        self.tree.column("size", width=95, anchor="e")
        self.tree.column("name", width=620)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.select_current())
        self.tree.bind("<Return>", lambda _e: self.select_current())

        yscroll = Scrollbar(body, orient="vertical", command=self.tree.yview)
        yscroll.pack(side=RIGHT, fill=Y)
        self.tree.configure(yscrollcommand=yscroll.set)

        bottom = Frame(self.window, padx=10, pady=8)
        bottom.pack(side=BOTTOM, fill=X)
        self.auto_status = StringVar(value="Auto-refreshing package list every 2 seconds.")
        Label(bottom, textvariable=self.auto_status).pack(side=LEFT)
        Button(bottom, text="Select", command=self.select_current).pack(side=RIGHT, padx=4)
        Button(bottom, text="Cancel", command=self.window.destroy).pack(side=RIGHT, padx=4)
        self.refresh()
        self.schedule_auto_refresh()

    def choose_folder(self) -> None:
        path = filedialog.askdirectory(title="Select package folder", initialdir=self.current_dir.get())
        if path:
            self.current_dir.set(path)
            self.refresh()

    @staticmethod
    def fmt_size(n: int) -> str:
        value = float(n)
        for unit in ["B", "KiB", "MiB", "GiB"]:
            if value < 1024 or unit == "GiB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{n} B"


    def scan_signature(self) -> tuple[tuple[str, int, int], ...]:
        folder = Path(self.current_dir.get()).expanduser()
        if not folder.exists():
            return tuple()
        text = self.filter_text.get().strip().lower()
        rows: list[tuple[str, int, int]] = []
        try:
            paths = [p for p in folder.iterdir() if is_supported_package(p)]
        except OSError:
            return tuple()
        if text:
            paths = [p for p in paths if text in p.name.lower()]
        for path in paths:
            try:
                st = path.stat()
            except OSError:
                continue
            rows.append((path.name, int(st.st_mtime), int(st.st_size)))
        rows.sort()
        return tuple(rows)

    def schedule_auto_refresh(self) -> None:
        if not self.window.winfo_exists():
            return
        self.window.after(self._auto_refresh_ms, self.auto_refresh_if_changed)

    def auto_refresh_if_changed(self) -> None:
        if not self.window.winfo_exists():
            return
        signature = self.scan_signature()
        if signature != self._last_scan_signature:
            self.refresh(auto=True)
        self.schedule_auto_refresh()

    def refresh(self, auto: bool = False) -> None:
        previous_name = ""
        sel = self.tree.selection()
        if sel:
            try:
                previous_name = self.files[int(sel[0])].name
            except Exception:
                previous_name = ""

        for item in self.tree.get_children():
            self.tree.delete(item)
        folder = Path(self.current_dir.get()).expanduser()
        if not folder.exists():
            self.files = []
            self._last_scan_signature = tuple()
            self.auto_status.set("Folder not found. Waiting for a valid package folder…")
            return
        text = self.filter_text.get().strip().lower()
        try:
            files = [p for p in folder.iterdir() if is_supported_package(p)]
        except OSError as exc:
            self.files = []
            self._last_scan_signature = tuple()
            self.auto_status.set(f"Could not read folder: {exc}")
            return
        if text:
            files = [p for p in files if text in p.name.lower()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        self.files = files
        restore_iid = ""
        for idx, path in enumerate(files):
            st = path.stat()
            mod = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            iid = str(idx)
            self.tree.insert("", END, iid=iid, values=(mod, self.fmt_size(st.st_size), path.name))
            if path.name == previous_name:
                restore_iid = iid

        self._last_scan_signature = self.scan_signature()
        if restore_iid:
            self.tree.selection_set(restore_iid)
            self.tree.see(restore_iid)
        elif files and auto:
            # A new newest package often appears while the picker is open; highlight it but do not deploy until selected.
            self.tree.selection_set("0")
            self.tree.see("0")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.auto_status.set(f"Newest files shown first. Auto-refreshed {stamp}. Double-click, Enter, or Select prompts deploy.")

    def select_current(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning(APP_TITLE, "Select a package first.")
            return
        self.on_select(str(self.files[int(sel[0])]))
        self.window.destroy()


class CommandModal:
    def __init__(self, parent: Tk, title: str) -> None:
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.geometry("980x620")
        self.window.transient(parent)

        self.command_var = StringVar(value="Preparing…")
        self.status_var = StringVar(value="Running…")
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.done = False
        self.exit_summary = ""
        self.auto_close_seconds = 30

        top = Frame(self.window, padx=10, pady=8)
        top.pack(side=TOP, fill=X)
        Label(top, text="Current command").pack(anchor="w")
        Entry(top, textvariable=self.command_var).pack(fill=X, pady=(2, 8))
        Label(top, textvariable=self.status_var).pack(anchor="w")

        body = Frame(self.window, padx=10)
        body.pack(side=TOP, fill=BOTH, expand=True)
        self.output_text = Text(body, wrap="word")
        self.output_text.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll = Scrollbar(body, orient="vertical", command=self.output_text.yview)
        yscroll.pack(side=RIGHT, fill=Y)
        self.output_text.configure(yscrollcommand=yscroll.set)

        bottom = Frame(self.window, padx=10, pady=8)
        bottom.pack(side=BOTTOM, fill=X)
        self.stop_btn = Button(bottom, text="Stop", command=self.stop)
        self.stop_btn.pack(side=LEFT)
        self.close_btn = Button(bottom, text="Close now", command=self.window.destroy, state="disabled")
        self.close_btn.pack(side=RIGHT)

        self.window.protocol("WM_DELETE_WINDOW", self.close_or_warn)
        self.window.after(100, self.drain)

    def set_command(self, cmd: str) -> None:
        self.command_var.set(cmd)

    def set_process(self, proc: subprocess.Popen[str]) -> None:
        self.process = proc

    def append(self, text: str) -> None:
        self.output_queue.put(text)

    def finish(self, code: int) -> None:
        self.done = True
        self.exit_summary = "Finished successfully." if code == 0 else f"Failed with exit code {code}."
        self.stop_btn.config(state="disabled")
        self.close_btn.config(state="normal")
        self.auto_close_seconds = 30
        self.countdown_close()

    def countdown_close(self) -> None:
        if not self.done or not self.window.winfo_exists():
            return
        if self.auto_close_seconds <= 0:
            self.window.destroy()
            return
        self.status_var.set(f"{self.exit_summary} Closing automatically in {self.auto_close_seconds} seconds.")
        self.auto_close_seconds -= 1
        self.window.after(1000, self.countdown_close)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.append("\n== Stop requested ==\n")
            self.process.terminate()

    def close_or_warn(self) -> None:
        if not self.done and self.process and self.process.poll() is None:
            messagebox.showwarning(APP_TITLE, "Deployment is still running. Use Stop first.")
            return
        self.window.destroy()

    def drain(self) -> None:
        while True:
            try:
                item = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self.output_text.insert(END, item)
            self.output_text.see(END)
        self.window.after(100, self.drain)


class DeployApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x800")

        self.package_path = StringVar()
        self.repo_parent = StringVar(value=str(Path.home() / "git" / "sports-website"))
        self.site_name = StringVar(value="sports")
        self.commit_message = StringVar(value="")
        self.watch_actions = BooleanVar(value=True)
        self.verbose_actions = BooleanVar(value=True)
        self.status = StringVar(value="Select a package to begin.")
        self.last_package_dir = default_download_dir()

        self.extract_dir: Path | None = None
        self.source_site_dir: Path | None = None
        self.dest_site_dir: Path | None = None
        self._auto_refresh_job: str | None = None
        self._suppress_package_trace = False

        self.build_ui()

    def build_ui(self) -> None:
        top = Frame(self.root, padx=10, pady=10)
        top.pack(side=TOP, fill=X)

        Label(top, text="Package file").grid(row=0, column=0, sticky="w")
        package_entry = Entry(top, textvariable=self.package_path, width=85)
        package_entry.grid(row=0, column=1, sticky="ew", padx=6)
        package_entry.bind("<Return>", lambda _e: self.refresh_script())
        package_entry.bind("<FocusOut>", lambda _e: self.schedule_auto_refresh_script(delay_ms=50))
        self.package_path.trace_add("write", lambda *_args: self.schedule_auto_refresh_script())
        Button(top, text="Browse…", command=self.choose_package).grid(row=0, column=2, padx=4)
        Button(top, text="Latest…", command=self.choose_latest_package).grid(row=0, column=3, padx=4)

        Label(top, text="Repo parent folder").grid(row=1, column=0, sticky="w")
        Entry(top, textvariable=self.repo_parent, width=85).grid(row=1, column=1, sticky="ew", padx=6)
        Button(top, text="Browse…", command=self.choose_repo_parent).grid(row=1, column=2, padx=4)

        Label(top, text="Site").grid(row=2, column=0, sticky="w")
        combo = ttk.Combobox(top, textvariable=self.site_name, values=["lroc", "sgars", "sports"], width=10, state="readonly")
        combo.grid(row=2, column=1, sticky="w", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_script())

        Label(top, text="Commit message").grid(row=3, column=0, sticky="w")
        Entry(top, textvariable=self.commit_message, width=85).grid(row=3, column=1, sticky="ew", padx=6, pady=(6, 0))
        Button(top, text="Refresh message", command=self.refresh_commit_message).grid(row=3, column=2, padx=4, pady=(6, 0))

        Checkbutton(
            top,
            text="Watch GitHub Actions after push (requires gh)",
            variable=self.watch_actions,
        ).grid(row=4, column=1, sticky="w", padx=6, pady=(6, 0))
        Checkbutton(
            top,
            text="Verbose Actions step/log output",
            variable=self.verbose_actions,
        ).grid(row=5, column=1, sticky="w", padx=6, pady=(2, 0))
        top.columnconfigure(1, weight=1)

        mid = Frame(self.root, padx=10)
        mid.pack(side=TOP, fill=BOTH, expand=True)

        left = Frame(mid)
        left.pack(side=LEFT, fill=BOTH, expand=True)
        Label(left, text="Deploy script preview/edit").pack(anchor="w")
        self.script_text = Text(left, wrap="none")
        self.script_text.pack(side=LEFT, fill=BOTH, expand=True)
        ys = Scrollbar(left, orient="vertical", command=self.script_text.yview)
        ys.pack(side=RIGHT, fill=Y)
        self.script_text.configure(yscrollcommand=ys.set)

        right = Frame(mid, padx=10)
        right.pack(side=RIGHT, fill=Y)
        Button(right, text="Extract / Refresh Script", width=25, command=self.refresh_script).pack(pady=4)
        Button(right, text="Show deploy file sample", width=25, command=self.show_sample).pack(pady=4)
        Button(right, text="Save sample file.deploy.txt", width=25, command=self.save_sample).pack(pady=4)
        Button(right, text="Deploy", width=25, command=self.deploy).pack(pady=(22, 4))
        Button(right, text="Quit", width=25, command=self.root.destroy).pack(pady=(22, 4))

        Label(right, text="Detected package contents").pack(anchor="w", pady=(18, 4))
        self.contents_list = Listbox(right, height=14, width=36)
        self.contents_list.pack(fill=Y)

        bottom = Frame(self.root, padx=10, pady=8)
        bottom.pack(side=BOTTOM, fill=X)
        Label(bottom, textvariable=self.status).pack(anchor="w")

    def choose_package(self) -> None:
        path = filedialog.askopenfilename(
            title="Select deployment package",
            initialdir=str(self.last_package_dir),
            filetypes=[("Deployment packages", "*.tar.gz *.tgz *.zip"), ("All files", "*.*")]
        )
        if path:
            self.set_package(path)

    def choose_latest_package(self) -> None:
        LatestPackageBrowser(self.root, self.last_package_dir, self.set_package_and_prompt_deploy)

    def set_package_and_prompt_deploy(self, path: str) -> None:
        """Select a package from the Latest picker, refresh the script, then show the normal deploy confirmation."""
        self.set_package(path)
        self.root.after(80, self.prompt_deploy_after_latest_select)

    def prompt_deploy_after_latest_select(self) -> None:
        if not self.package_path.get().strip():
            return
        try:
            self.refresh_commit_message()
            self.refresh_script(show_errors=True)
        except Exception as exc:
            self.status.set(f"Ready-to-deploy refresh failed: {exc}")
            return
        self.deploy()

    def set_package(self, path: str) -> None:
        self._suppress_package_trace = True
        try:
            self.package_path.set(path)
        finally:
            self._suppress_package_trace = False
        self.last_package_dir = Path(path).expanduser().parent
        self.refresh_commit_message()
        self.schedule_auto_refresh_script(delay_ms=10)

    def schedule_auto_refresh_script(self, delay_ms: int = 350) -> None:
        if self._suppress_package_trace:
            return
        raw = self.package_path.get().strip()
        if not raw:
            return
        package = Path(raw).expanduser()
        # While the user is typing/pasting a path, wait until it is a real supported package.
        if not is_supported_package(package):
            return
        if self._auto_refresh_job:
            try:
                self.root.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
        self._auto_refresh_job = self.root.after(delay_ms, self._run_auto_refresh_script)

    def _run_auto_refresh_script(self) -> None:
        self._auto_refresh_job = None
        if not self.package_path.get().strip():
            return
        try:
            self.refresh_commit_message()
            self.refresh_script(show_errors=False)
        except Exception as exc:
            self.status.set(f"Auto extract/refresh failed: {exc}")

    def refresh_commit_message(self) -> None:
        if self.package_path.get():
            self.commit_message.set(infer_commit_message(self.package_path.get(), self.site_name.get()))

    def choose_repo_parent(self) -> None:
        path = filedialog.askdirectory(title="Select repo parent folder, e.g. ~/git/sports-website")
        if path:
            self.repo_parent.set(path)
            self.refresh_script()

    def extract_package(self) -> None:
        package = Path(self.package_path.get()).expanduser()
        if not package.exists():
            raise FileNotFoundError(f"Package not found: {package}")
        if not is_supported_package(package):
            raise ValueError("Select a .tar.gz, .tgz, or .zip package.")

        if self.extract_dir and self.extract_dir.exists():
            shutil.rmtree(self.extract_dir, ignore_errors=True)

        self.extract_dir = Path(tempfile.mkdtemp(prefix="site-deploy-"))

        if str(package).endswith((".tar.gz", ".tgz")):
            with tarfile.open(package, "r:gz") as tf:
                self.safe_extract_tar(tf, self.extract_dir)
        else:
            with zipfile.ZipFile(package) as zf:
                self.safe_extract_zip(zf, self.extract_dir)

        site = self.site_name.get()
        candidates = list(self.extract_dir.glob(site))
        if not candidates:
            candidates = [p for p in self.extract_dir.iterdir() if p.is_dir() and p.name in {"lroc", "sgars", "sports"}]
        if not candidates:
            raise FileNotFoundError("Could not find lroc/, sgars/, or sports/ folder inside package.")

        self.source_site_dir = candidates[0]
        self.site_name.set(self.source_site_dir.name)
        self.dest_site_dir = Path(self.repo_parent.get()).expanduser() / self.source_site_dir.name

        self.contents_list.delete(0, END)
        for child in sorted(self.source_site_dir.iterdir(), key=lambda p: p.name.lower()):
            self.contents_list.insert(END, child.name + ("/" if child.is_dir() else ""))

    @staticmethod
    def safe_extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
        root = dest.resolve()
        for member in tf.getmembers():
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(root)):
                raise RuntimeError(f"Unsafe tar path blocked: {member.name}")
        tf.extractall(dest)

    @staticmethod
    def safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
        root = dest.resolve()
        for name in zf.namelist():
            target = (dest / name).resolve()
            if not str(target).startswith(str(root)):
                raise RuntimeError(f"Unsafe zip path blocked: {name}")
        zf.extractall(dest)

    def values(self) -> dict[str, str]:
        package = Path(self.package_path.get()).expanduser()
        commit = self.commit_message.get().strip() or infer_commit_message(str(package), self.site_name.get())
        return {
            "package_path": str(package),
            "extract_dir": str(self.extract_dir or ""),
            "source_site_dir": str(self.source_site_dir or ""),
            "dest_parent_dir": str(Path(self.repo_parent.get()).expanduser()),
            "dest_site_dir": str(self.dest_site_dir or ""),
            "site_name": self.site_name.get(),
            "commit_message": commit,
            "commit_message_quoted": shell_quote(commit),
        }

    def render_script(self) -> str:
        if not self.source_site_dir or not self.dest_site_dir or not self.extract_dir:
            raise RuntimeError("Package has not been extracted.")
        vals = self.values()
        deploy_file = self.source_site_dir / "file.deploy.txt"
        if deploy_file.exists():
            script = deploy_file.read_text(encoding="utf-8")
            return replace_placeholders(script, vals)
        return DEFAULT_DEPLOY_TEMPLATE.format(**vals)

    def refresh_script(self, show_errors: bool = True) -> None:
        if self._auto_refresh_job:
            try:
                self.root.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
            self._auto_refresh_job = None
        if not self.package_path.get():
            return
        try:
            self.extract_package()
            script = self.render_script()
            self.script_text.delete("1.0", END)
            self.script_text.insert("1.0", script)
            leftovers = sorted(set(PLACEHOLDER_RE.findall(script)))
            source = "package file.deploy.txt" if (self.source_site_dir / "file.deploy.txt").exists() else "generated script"
            extra = f"; unresolved placeholders: {', '.join(leftovers)}" if leftovers else ""
            self.status.set(f"Ready: extracted to {self.source_site_dir}; using {source}{extra}.")
        except Exception as exc:
            self.status.set(f"Error: {exc}")
            if show_errors:
                messagebox.showerror(APP_TITLE, str(exc))

    def show_sample(self) -> None:
        win = Toplevel(self.root)
        win.title("Sample file.deploy.txt")
        win.geometry("940x640")
        text = Text(win, wrap="none")
        text.pack(fill=BOTH, expand=True)
        text.insert("1.0", SAMPLE_DEPLOY)
        Button(win, text="Close", command=win.destroy).pack(pady=5)

    def save_sample(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save sample file.deploy.txt",
            initialfile="file.deploy.txt",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            Path(path).write_text(SAMPLE_DEPLOY, encoding="utf-8")
            messagebox.showinfo(APP_TITLE, f"Saved:\n{path}")

    def deploy(self) -> None:
        script = self.script_text.get("1.0", END).strip()
        script = replace_placeholders(script, self.values()).strip()

        self.script_text.delete("1.0", END)
        self.script_text.insert("1.0", script)

        if not script:
            messagebox.showwarning(APP_TITLE, "No deploy script to run.")
            return

        leftovers = sorted(set(PLACEHOLDER_RE.findall(script)))
        if leftovers:
            messagebox.showerror(APP_TITLE, "Deploy blocked. Unresolved placeholders:\n\n" + "\n".join(leftovers))
            return

        if script_has_active_rsync_delete(script):
            if not messagebox.askyesno(APP_TITLE, "Script contains an active --delete option. This can remove local-only files. Continue?"):
                return

        if not messagebox.askyesno(APP_TITLE, f"Run deploy with commit message:\n\n{self.commit_message.get().strip()}"):
            return

        modal = CommandModal(self.root, f"Deploying {self.site_name.get()}")
        watch_actions = bool(self.watch_actions.get())
        threading.Thread(target=self.run_script, args=(script, modal, watch_actions), daemon=True).start()

    def run_script(self, script: str, modal: CommandModal, watch_actions: bool) -> None:
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="site-deploy-run-"))
            temp_script = temp_dir / "deploy.sh"
            temp_script.write_text(script + "\n", encoding="utf-8")
            temp_script.chmod(0o700)

            cmd = f"bash {shlex.quote(str(temp_script))}"
            modal.set_command(cmd)
            modal.append(f"$ {cmd}\n\n")

            proc = subprocess.Popen(
                ["bash", str(temp_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(Path(self.repo_parent.get()).expanduser()),
                env=os.environ.copy(),
            )
            modal.set_process(proc)
            assert proc.stdout is not None
            for line in proc.stdout:
                modal.append(line)
            code = proc.wait()
            modal.append(f"\n== Local deploy exit code: {code} ==\n")

            final_code = code
            if code == 0 and watch_actions:
                final_code = self.watch_github_actions(modal)
            elif code == 0:
                modal.append("\n== GitHub Actions watch disabled ==\n")

            modal.finish(final_code)
            if final_code == 0:
                self.status.set("Deploy finished." if not watch_actions else "Deploy and GitHub Actions finished.")
            elif code == 0 and watch_actions:
                self.status.set(f"GitHub Actions failed or timed out with exit code {final_code}.")
            else:
                self.status.set(f"Deploy failed with exit code {code}.")
        except Exception as exc:
            modal.append(f"\nERROR: {exc}\n")
            modal.finish(1)
            self.status.set(f"Deploy error: {exc}")


    @staticmethod
    def run_captured(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=os.environ.copy(),
        )

    def read_json_command(self, args: list[str], cwd: Path, modal: CommandModal, timeout: int = 30):
        try:
            result = self.run_captured(args, cwd, timeout=timeout)
        except subprocess.TimeoutExpired:
            modal.append(f"[{aest_stamp()}] Command timed out: {' '.join(args)}\n")
            return None
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            modal.append(f"[{aest_stamp()}] Command failed: {' '.join(args)}\n")
            if details:
                modal.append(details + "\n")
            return None
        try:
            return json.loads(result.stdout or "null")
        except json.JSONDecodeError as exc:
            modal.append(f"[{aest_stamp()}] Could not parse gh JSON: {exc}\n")
            modal.append((result.stdout or "").strip() + "\n")
            return None

    def detect_head_sha(self, repo_dir: Path, modal: CommandModal) -> str | None:
        result = self.run_captured(["git", "rev-parse", "HEAD"], repo_dir)
        if result.returncode != 0:
            modal.append(f"[{aest_stamp()}] Could not determine git HEAD. GitHub Actions watch skipped.\n")
            if result.stderr.strip():
                modal.append(result.stderr.strip() + "\n")
            return None
        return result.stdout.strip()

    def get_action_runs_for_commit(self, repo_dir: Path, sha: str, modal: CommandModal) -> list[dict]:
        # Some installed gh versions do not support `gh run list --commit`.
        # Use the stable JSON output and filter by headSha locally instead.
        data = self.read_json_command(
            [
                "gh", "run", "list",
                "--limit", "50",
                "--json", "databaseId,name,status,conclusion,workflowName,createdAt,url,headSha,event",
            ],
            repo_dir,
            modal,
            timeout=30,
        )
        if not isinstance(data, list):
            return []
        matches = [run for run in data if (run.get("headSha") or "").lower() == sha.lower()]
        # New runs can take a few seconds to appear; return only true matches so the
        # watcher waits rather than attaching to an unrelated recent deployment.
        return matches

    def get_action_run_details(self, repo_dir: Path, run_id: int, modal: CommandModal) -> dict | None:
        data = self.read_json_command(
            [
                "gh", "run", "view", str(run_id),
                "--json", "databaseId,name,status,conclusion,workflowName,url,jobs",
            ],
            repo_dir,
            modal,
            timeout=30,
        )
        return data if isinstance(data, dict) else None

    def append_failed_action_logs(self, repo_dir: Path, run_id: int, modal: CommandModal) -> None:
        modal.append(f"\n== GitHub Actions failed log excerpt for run {run_id} ==\n")
        try:
            result = self.run_captured(["gh", "run", "view", str(run_id), "--log-failed"], repo_dir, timeout=90)
        except subprocess.TimeoutExpired:
            modal.append(f"[{aest_stamp()}] Timed out while fetching failed action logs.\n")
            return
        output = (result.stdout or result.stderr or "").strip()
        if output:
            modal.append(output + "\n")
        else:
            modal.append("No failed-step log was returned by gh.\n")

    def append_final_action_log(self, repo_dir: Path, run_id: int, modal: CommandModal) -> None:
        if not self.verbose_actions.get():
            return
        modal.append(f"\n== GitHub Actions full log for run {run_id} ==\n")
        modal.append(f"[{aest_stamp()}] Fetching workflow log via gh run view --log.\n")
        try:
            result = self.run_captured(["gh", "run", "view", str(run_id), "--log"], repo_dir, timeout=180)
        except subprocess.TimeoutExpired:
            modal.append(f"[{aest_stamp()}] Timed out while fetching full action log.\n")
            return
        output = strip_terminal_control(result.stdout or result.stderr or "").strip()
        if not output:
            modal.append("No workflow log was returned by gh.\n")
            return
        if len(output) > MAX_FINAL_ACTION_LOG_CHARS:
            modal.append(
                output[:MAX_FINAL_ACTION_LOG_CHARS]
                + f"\n\n[log truncated at {MAX_FINAL_ACTION_LOG_CHARS:,} chars by deploy helper]\n"
            )
        else:
            modal.append(output + "\n")

    def append_live_job_log_delta(
        self,
        repo_dir: Path,
        run_id: int,
        job: dict,
        modal: CommandModal,
        last_log_pos: dict[tuple[int, str], int],
        log_announced: set[tuple[int, str]],
        log_unavailable_noted: set[tuple[int, str]],
    ) -> None:
        """Stream the same job log content visible in the GitHub Actions browser view.

        GitHub only exposes logs that have been flushed by Actions, so this is
        implemented as a safe poll-and-diff. It prints only new log text for each
        job and keeps running even if the log endpoint is briefly unavailable.
        """
        if not self.verbose_actions.get():
            return

        job_id = job.get("databaseId") or job.get("id")
        if not job_id:
            return
        job_key = (run_id, str(job_id))

        # Avoid hammering jobs that have not started yet.
        job_status = job.get("status") or ""
        if job_status not in {"in_progress", "completed"}:
            return

        try:
            result = self.run_captured(
                ["gh", "run", "view", str(run_id), "--job", str(job_id), "--log"],
                repo_dir,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            if job_key not in log_unavailable_noted:
                modal.append(f"[{aest_stamp()}]   Job log not ready yet for job {job_id}; will retry.\n")
                log_unavailable_noted.add(job_key)
            return

        raw_output = result.stdout or result.stderr or ""
        output = strip_terminal_control(raw_output)
        if result.returncode != 0 or not output.strip():
            if job_key not in log_unavailable_noted:
                modal.append(f"[{aest_stamp()}]   Job log not available yet for job {job_id}; will retry.\n")
                log_unavailable_noted.add(job_key)
            return

        previous = last_log_pos.get(job_key, 0)
        if previous > len(output):
            # GitHub can occasionally return a shorter partial log while a job is
            # still running. Reset rather than losing output forever.
            previous = 0

        delta = output[previous:]
        if not delta.strip():
            return

        if job_key not in log_announced:
            job_name = job.get("name") or str(job_id)
            modal.append(f"\n== Live GitHub Actions log: {job_name} ==\n")
            log_announced.add(job_key)

        if len(delta) > MAX_LIVE_ACTION_LOG_CHARS_PER_POLL:
            delta = (
                delta[-MAX_LIVE_ACTION_LOG_CHARS_PER_POLL:]
                + f"\n[live log delta truncated to last {MAX_LIVE_ACTION_LOG_CHARS_PER_POLL:,} chars by deploy helper]\n"
            )

        modal.append(delta if delta.endswith("\n") else delta + "\n")
        last_log_pos[job_key] = len(output)

    @staticmethod
    def describe_step(step: dict, index: int) -> tuple[str, str, str, str]:
        number = step.get("number") or step.get("index") or index
        name = step.get("name") or f"step {number}"
        status = step.get("status") or step.get("state") or "unknown"
        conclusion = step.get("conclusion") or ""
        extra_parts = []
        if step.get("startedAt"):
            extra_parts.append(f"started {step.get('startedAt')}")
        if step.get("completedAt"):
            extra_parts.append(f"completed {step.get('completedAt')}")
        return str(number), str(name), str(status), str(conclusion or "")

    def append_step_changes(
        self,
        run_id: int,
        job_name: str,
        job: dict,
        modal: CommandModal,
        last_step_state: dict[tuple[int, str, str], tuple[str, str]],
    ) -> None:
        if not self.verbose_actions.get():
            return
        steps = job.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return
        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            number, step_name, status, conclusion = self.describe_step(step, idx)
            step_key = (run_id, job_name, f"{number}:{step_name}")
            step_state = (status, conclusion)
            if last_step_state.get(step_key) == step_state:
                continue
            suffix = f" / {conclusion}" if conclusion else ""
            modal.append(f"[{aest_stamp()}]     Step {number}: {step_name}: {status}{suffix}\n")
            last_step_state[step_key] = step_state

    def watch_github_actions(self, modal: CommandModal) -> int:
        repo_dir = Path(self.repo_parent.get()).expanduser()
        modal.append("\n== GitHub Actions watch ==\n")
        modal.append(f"[{aest_stamp()}] Preparing to watch GitHub Actions for this push.\n")

        if not shutil.which("gh"):
            modal.append(
                f"[{aest_stamp()}] GitHub CLI 'gh' was not found. "
                "Install/authenticate gh to watch Actions from this helper.\n"
            )
            return 0

        auth = self.run_captured(["gh", "auth", "status"], repo_dir, timeout=30)
        if auth.returncode != 0:
            modal.append(f"[{aest_stamp()}] gh is installed but not authenticated. GitHub Actions watch skipped.\n")
            if auth.stderr.strip():
                modal.append(auth.stderr.strip() + "\n")
            return 0

        sha = self.detect_head_sha(repo_dir, modal)
        if not sha:
            return 0
        short_sha = sha[:12]
        modal.append(f"[{aest_stamp()}] Watching workflow runs for commit {short_sha}.\n")

        runs: list[dict] = []
        appear_deadline = time.monotonic() + GITHUB_ACTIONS_APPEAR_TIMEOUT_SECONDS
        while time.monotonic() < appear_deadline:
            runs = self.get_action_runs_for_commit(repo_dir, sha, modal)
            if runs:
                break
            modal.append(f"[{aest_stamp()}] No workflow run has appeared yet; waiting...\n")
            time.sleep(GITHUB_ACTIONS_POLL_SECONDS)

        if not runs:
            modal.append(
                f"[{aest_stamp()}] No GitHub Actions runs appeared for {short_sha} "
                f"within {GITHUB_ACTIONS_APPEAR_TIMEOUT_SECONDS} seconds.\n"
            )
            return 0

        run_ids = []
        for run in runs:
            run_id = run.get("databaseId")
            if not run_id:
                continue
            run_ids.append(int(run_id))
            workflow = run.get("workflowName") or "Workflow"
            title = run.get("displayTitle") or run.get("name") or "untitled run"
            url = run.get("url") or ""
            modal.append(f"[{aest_stamp()}] Found Actions run {run_id}: {workflow} — {title}\n")
            if url:
                modal.append(f"    {url}\n")

        if not run_ids:
            modal.append(f"[{aest_stamp()}] gh returned runs, but no run IDs were usable. Watch skipped.\n")
            return 0

        if self.verbose_actions.get():
            modal.append(f"[{aest_stamp()}] Verbose Actions output enabled: browser-style job logs and step state changes will be printed.\n")

        last_run_state: dict[int, tuple[str, str]] = {}
        last_job_state: dict[tuple[int, str], tuple[str, str]] = {}
        last_step_state: dict[tuple[int, str, str], tuple[str, str]] = {}
        any_failed = False
        failed_logs_printed: set[int] = set()
        last_live_log_pos: dict[tuple[int, str], int] = {}
        live_log_announced: set[tuple[int, str]] = set()
        live_log_unavailable_noted: set[tuple[int, str]] = set()
        watch_deadline = time.monotonic() + GITHUB_ACTIONS_WATCH_TIMEOUT_SECONDS

        while time.monotonic() < watch_deadline:
            all_done = True
            for run_id in run_ids:
                details = self.get_action_run_details(repo_dir, run_id, modal)
                if not details:
                    all_done = False
                    continue

                status = details.get("status") or "unknown"
                conclusion = details.get("conclusion") or ""
                workflow = details.get("workflowName") or "Workflow"
                title = details.get("displayTitle") or details.get("name") or "untitled run"
                run_state = (status, conclusion)

                if last_run_state.get(run_id) != run_state:
                    suffix = f" / {conclusion}" if conclusion else ""
                    modal.append(f"[{aest_stamp()}] Run {run_id} {workflow}: {status}{suffix} — {title}\n")
                    last_run_state[run_id] = run_state

                for job in details.get("jobs") or []:
                    job_name = job.get("name") or str(job.get("databaseId") or "job")
                    job_status = job.get("status") or "unknown"
                    job_conclusion = job.get("conclusion") or ""
                    job_key = (run_id, job_name)
                    job_state = (job_status, job_conclusion)
                    if last_job_state.get(job_key) != job_state:
                        suffix = f" / {job_conclusion}" if job_conclusion else ""
                        modal.append(f"[{aest_stamp()}]   Job: {job_name}: {job_status}{suffix}\n")
                        last_job_state[job_key] = job_state

                    self.append_step_changes(run_id, job_name, job, modal, last_step_state)
                    self.append_live_job_log_delta(
                        repo_dir,
                        run_id,
                        job,
                        modal,
                        last_live_log_pos,
                        live_log_announced,
                        live_log_unavailable_noted,
                    )

                if status != "completed":
                    all_done = False
                elif conclusion not in ("success", "skipped", "neutral"):
                    any_failed = True
                    if run_id not in failed_logs_printed:
                        self.append_failed_action_logs(repo_dir, run_id, modal)
                        failed_logs_printed.add(run_id)

            if all_done:
                if self.verbose_actions.get():
                    for run_id in run_ids:
                        self.append_final_action_log(repo_dir, run_id, modal)
                if any_failed:
                    modal.append(f"[{aest_stamp()}] GitHub Actions completed with failures.\n")
                    return 1
                modal.append(f"[{aest_stamp()}] GitHub Actions completed successfully.\n")
                return 0

            time.sleep(GITHUB_ACTIONS_POLL_SECONDS)

        modal.append(
            f"[{aest_stamp()}] GitHub Actions watch timed out after "
            f"{GITHUB_ACTIONS_WATCH_TIMEOUT_SECONDS // 60} minutes.\n"
        )
        return 1


def main() -> None:
    root = Tk()
    DeployApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
