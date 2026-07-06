#!/usr/bin/env python3
"""
Sports.vk2ale Local Admin Manager

A local-only Tkinter tool for administering the Sports.vk2ale DynamoDB catalogue.
It uses your local AWS credentials/profile through boto3. It does not expose a
public admin website and does not require Cognito.

Run:
  python3 sports/admin_manager/sports_admin_manager.py

Optional:
  AWS_PROFILE=my-profile python3 sports/admin_manager/sports_admin_manager.py
"""

from __future__ import annotations

import json
import os
import re
import threading
import traceback
import webbrowser
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, TOP, BOTTOM, X, Y, BooleanVar, StringVar, Text, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound
except Exception:  # pragma: no cover - shown as a GUI error at startup
    boto3 = None
    BotoCoreError = ClientError = NoCredentialsError = ProfileNotFound = Exception


APP_TITLE = "Sports.vk2ale Local Admin Manager"
DEFAULT_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
DEFAULT_PROJECT = os.environ.get("SPORTS_PROJECT_NAME", "sports-aggregator")
DEFAULT_ENV = os.environ.get("SPORTS_ENVIRONMENT", "dev")
DEFAULT_PROFILE = os.environ.get("AWS_PROFILE", "")

COLLECTIONS = {
    "suggestions": {
        "label": "Suggestions",
        "suffix": "suggestions",
        "sort": ["status", "submitted_at", "name"],
    },
    "sport_bodies": {
        "label": "Official bodies",
        "suffix": "sport-bodies",
        "sort": ["sport", "name"],
    },
    "top_players": {
        "label": "Top players",
        "suffix": "top-players",
        "sort": ["sport", "name"],
    },
    "pathways": {
        "label": "Pathways",
        "suffix": "players",
        "sort": ["sport", "name"],
    },
    "tournaments": {
        "label": "Tournaments",
        "suffix": "tournaments",
        "sort": ["start_date", "name"],
    },
    "events": {
        "label": "Events",
        "suffix": "events",
        "sort": ["date", "name"],
    },
}


class JsonDecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def normalize_decimal(value):
    """Convert floats to Decimal for DynamoDB and recurse through containers."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(k): normalize_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_decimal(v) for v in value]
    return value


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def slugify(value: str, prefix: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = f"item-{int(datetime.now(timezone.utc).timestamp())}"
    return f"{prefix}{slug}" if prefix else slug


def get_text_preview(item: dict, *fields: str) -> str:
    for field in fields:
        value = item.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def sort_items(items: list[dict], fields: list[str]) -> list[dict]:
    def key(item: dict):
        return tuple(str(item.get(field, "")).lower() for field in fields)
    return sorted(items, key=key)


@dataclass
class AwsConfig:
    profile: str
    region: str
    project_name: str
    environment: str

    @property
    def prefix(self) -> str:
        return f"{self.project_name}-{self.environment}"

    def table_name(self, collection: str) -> str:
        suffix = COLLECTIONS[collection]["suffix"]
        return f"{self.prefix}-{suffix}"


class DynamoAdminClient:
    def __init__(self, config: AwsConfig) -> None:
        if boto3 is None:
            raise RuntimeError("boto3 is not installed. Run: python3 -m pip install boto3")
        self.config = config
        if config.profile:
            self.session = boto3.Session(profile_name=config.profile, region_name=config.region)
        else:
            self.session = boto3.Session(region_name=config.region)
        self.ddb = self.session.resource("dynamodb")
        self.sts = self.session.client("sts")

    def caller_identity(self) -> dict:
        return self.sts.get_caller_identity()

    def table(self, collection: str):
        return self.ddb.Table(self.config.table_name(collection))

    def scan_all(self, collection: str) -> list[dict]:
        table = self.table(collection)
        items: list[dict] = []
        kwargs: dict = {}
        while True:
            response = table.scan(**kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return sort_items(items, COLLECTIONS[collection]["sort"])
            kwargs["ExclusiveStartKey"] = last_key

    def get_item(self, collection: str, item_id: str) -> dict | None:
        result = self.table(collection).get_item(Key={"id": item_id})
        return result.get("Item")

    def put_item(self, collection: str, item: dict) -> None:
        if not item.get("id"):
            raise ValueError("Item must contain an id")
        item = deepcopy(item)
        item.setdefault("created_at", now_iso())
        item["updated_at"] = now_iso()
        self.table(collection).put_item(Item=normalize_decimal(item))

    def delete_item(self, collection: str, item_id: str) -> None:
        self.table(collection).delete_item(Key={"id": item_id})

    def update_suggestion_status(self, suggestion_id: str, status: str, extra: dict | None = None) -> None:
        item = self.get_item("suggestions", suggestion_id)
        if not item:
            raise ValueError(f"Suggestion not found: {suggestion_id}")
        item["status"] = status
        item["reviewed_at"] = now_iso()
        item["updated_at"] = now_iso()
        if extra:
            item.update(extra)
        self.table("suggestions").put_item(Item=normalize_decimal(item))


class JsonEditor(Toplevel):
    def __init__(self, parent: Tk, title: str, initial: dict, on_save) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("920x720")
        self.transient(parent)
        self.on_save = on_save

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text="Edit JSON. Save validates JSON and writes to DynamoDB.").pack(anchor="w")

        body = ttk.Frame(frame)
        body.pack(fill=BOTH, expand=True, pady=(8, 8))
        self.text = Text(body, wrap="none", undo=True)
        self.text.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        yscroll.pack(side=RIGHT, fill=Y)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.insert("1.0", json.dumps(initial, cls=JsonDecimalEncoder, indent=2, sort_keys=True))

        buttons = ttk.Frame(frame)
        buttons.pack(fill=X)
        ttk.Button(buttons, text="Save", command=self.save).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=RIGHT)

    def save(self) -> None:
        try:
            payload = json.loads(self.text.get("1.0", END))
            if not isinstance(payload, dict):
                raise ValueError("Top-level JSON must be an object")
            self.on_save(payload)
            self.destroy()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not save JSON:\n\n{exc}", parent=self)


class SportsAdminApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1260x820")
        self.client: DynamoAdminClient | None = None
        self.items: dict[str, list[dict]] = {key: [] for key in COLLECTIONS}
        self.selected_suggestion: dict | None = None
        self.selected_record: dict | None = None

        self.profile_var = StringVar(value=DEFAULT_PROFILE)
        self.region_var = StringVar(value=DEFAULT_REGION)
        self.project_var = StringVar(value=DEFAULT_PROJECT)
        self.env_var = StringVar(value=DEFAULT_ENV)
        self.status_filter_var = StringVar(value="pending_review")
        self.record_collection_var = StringVar(value="sport_bodies")
        self.record_search_var = StringVar(value="")
        self.include_all_suggestions_var = BooleanVar(value=False)
        self.status_var = StringVar(value="Not connected.")

        self.build_ui()

    def build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=TOP, fill=X)
        ttk.Label(top, text="AWS profile").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.profile_var, width=18).grid(row=0, column=1, padx=(4, 12), sticky="w")
        ttk.Label(top, text="Region").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.region_var, width=18).grid(row=0, column=3, padx=(4, 12), sticky="w")
        ttk.Label(top, text="Project").grid(row=0, column=4, sticky="w")
        ttk.Entry(top, textvariable=self.project_var, width=22).grid(row=0, column=5, padx=(4, 12), sticky="w")
        ttk.Label(top, text="Environment").grid(row=0, column=6, sticky="w")
        ttk.Entry(top, textvariable=self.env_var, width=10).grid(row=0, column=7, padx=(4, 12), sticky="w")
        ttk.Button(top, text="Connect / refresh", command=self.connect_and_refresh).grid(row=0, column=8, sticky="e")
        top.columnconfigure(9, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))
        self.build_suggestions_tab()
        self.build_records_tab()
        self.build_backup_tab()

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(side=BOTTOM, fill=X)
        ttk.Label(bottom, textvariable=self.status_var).pack(side=LEFT, fill=X, expand=True)

    def build_suggestions_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Suggestions")

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X)
        ttk.Label(toolbar, text="Status").pack(side=LEFT)
        status_combo = ttk.Combobox(
            toolbar,
            textvariable=self.status_filter_var,
            values=["pending_review", "approved", "rejected", "all"],
            width=18,
            state="readonly",
        )
        status_combo.pack(side=LEFT, padx=(4, 10))
        status_combo.bind("<<ComboboxSelected>>", lambda _e: self.populate_suggestions())
        ttk.Button(toolbar, text="Refresh", command=lambda: self.refresh_collection("suggestions")).pack(side=LEFT)
        ttk.Button(toolbar, text="Open URL", command=self.open_suggestion_url).pack(side=LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Approve as official body", command=self.approve_suggestion_as_body).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="Approve as pathway", command=self.approve_suggestion_as_pathway).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="Reject", command=self.reject_suggestion).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="Delete", command=self.delete_suggestion).pack(side=RIGHT, padx=(8, 0))

        main = ttk.Panedwindow(tab, orient="horizontal")
        main.pack(fill=BOTH, expand=True, pady=(10, 0))

        left = ttk.Frame(main)
        main.add(left, weight=3)
        columns = ("status", "name", "sport", "type", "submitted")
        self.suggestions_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for col, label, width in [
            ("status", "Status", 125),
            ("name", "Name", 260),
            ("sport", "Sport", 140),
            ("type", "Type", 120),
            ("submitted", "Submitted", 180),
        ]:
            self.suggestions_tree.heading(col, text=label)
            self.suggestions_tree.column(col, width=width, anchor="w")
        self.suggestions_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.suggestions_tree.bind("<<TreeviewSelect>>", self.on_suggestion_select)
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.suggestions_tree.yview)
        yscroll.pack(side=RIGHT, fill=Y)
        self.suggestions_tree.configure(yscrollcommand=yscroll.set)

        right = ttk.Frame(main)
        main.add(right, weight=2)
        ttk.Label(right, text="Suggestion details").pack(anchor="w")
        self.suggestion_detail = Text(right, height=18, wrap="word")
        self.suggestion_detail.pack(fill=BOTH, expand=True, pady=(6, 0))

    def build_records_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Curated records")

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X)
        ttk.Label(toolbar, text="Collection").pack(side=LEFT)
        values = list(COLLECTIONS.keys())
        record_combo = ttk.Combobox(toolbar, textvariable=self.record_collection_var, values=values, width=18, state="readonly")
        record_combo.pack(side=LEFT, padx=(4, 10))
        record_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_selected_record_collection())
        ttk.Label(toolbar, text="Filter").pack(side=LEFT)
        filter_entry = ttk.Entry(toolbar, textvariable=self.record_search_var, width=32)
        filter_entry.pack(side=LEFT, padx=(4, 8))
        filter_entry.bind("<KeyRelease>", lambda _e: self.populate_records())
        ttk.Button(toolbar, text="Refresh", command=self.refresh_selected_record_collection).pack(side=LEFT)
        ttk.Button(toolbar, text="New", command=self.new_record).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="Edit JSON", command=self.edit_selected_record).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="Open URL", command=self.open_record_url).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="Delete", command=self.delete_selected_record).pack(side=RIGHT, padx=(8, 0))

        main = ttk.Panedwindow(tab, orient="horizontal")
        main.pack(fill=BOTH, expand=True, pady=(10, 0))
        left = ttk.Frame(main)
        main.add(left, weight=3)
        columns = ("id", "name", "sport", "updated")
        self.records_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for col, label, width in [
            ("id", "ID", 250),
            ("name", "Name", 260),
            ("sport", "Sport", 130),
            ("updated", "Updated", 180),
        ]:
            self.records_tree.heading(col, text=label)
            self.records_tree.column(col, width=width, anchor="w")
        self.records_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.records_tree.bind("<<TreeviewSelect>>", self.on_record_select)
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.records_tree.yview)
        yscroll.pack(side=RIGHT, fill=Y)
        self.records_tree.configure(yscrollcommand=yscroll.set)

        right = ttk.Frame(main)
        main.add(right, weight=2)
        ttk.Label(right, text="Record preview").pack(anchor="w")
        self.record_detail = Text(right, height=18, wrap="word")
        self.record_detail.pack(fill=BOTH, expand=True, pady=(6, 0))

    def build_backup_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Backup / import")

        info = (
            "Export writes the current DynamoDB catalogue to a JSON file. "
            "Import reads a JSON file with collection keys such as sport_bodies, top_players, pathways, "
            "tournaments, events and suggestions, then upserts those items by id."
        )
        ttk.Label(tab, text=info, wraplength=980, justify="left").pack(anchor="w")

        buttons = ttk.Frame(tab)
        buttons.pack(fill=X, pady=(16, 10))
        ttk.Button(buttons, text="Export all tables to JSON", command=self.export_all).pack(side=LEFT)
        ttk.Button(buttons, text="Import JSON into selected tables", command=self.import_json).pack(side=LEFT, padx=(10, 0))

        ttk.Label(tab, text="Activity log").pack(anchor="w", pady=(10, 4))
        self.log_text = Text(tab, height=24, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}\n"
        if hasattr(self, "log_text"):
            self.log_text.insert(END, line)
            self.log_text.see(END)
        self.status_var.set(message)

    def get_config(self) -> AwsConfig:
        return AwsConfig(
            profile=self.profile_var.get().strip(),
            region=self.region_var.get().strip() or DEFAULT_REGION,
            project_name=self.project_var.get().strip() or DEFAULT_PROJECT,
            environment=self.env_var.get().strip() or DEFAULT_ENV,
        )

    def run_background(self, label: str, func, on_done=None) -> None:
        self.status_var.set(f"Running: {label}…")
        def worker():
            try:
                result = func()
            except Exception as exc:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self.handle_error(label, exc, tb))
                return
            if on_done:
                self.root.after(0, lambda: on_done(result))
            else:
                self.root.after(0, lambda: self.log(f"Finished: {label}"))
        threading.Thread(target=worker, daemon=True).start()

    def handle_error(self, label: str, exc: Exception, tb: str) -> None:
        self.log(f"{label} failed: {exc}")
        if hasattr(self, "log_text"):
            self.log_text.insert(END, tb + "\n")
            self.log_text.see(END)
        messagebox.showerror(APP_TITLE, f"{label} failed:\n\n{exc}")

    def connect_and_refresh(self) -> None:
        def task():
            config = self.get_config()
            client = DynamoAdminClient(config)
            identity = client.caller_identity()
            # Eagerly scan small catalogue tables for a clear connection test.
            items = {collection: client.scan_all(collection) for collection in COLLECTIONS}
            return client, identity, items

        def done(result):
            self.client, identity, self.items = result
            self.log(f"Connected as {identity.get('Arn')} using prefix {self.client.config.prefix}.")
            self.populate_suggestions()
            self.populate_records()

        self.run_background("Connect and refresh", task, done)

    def require_client(self) -> DynamoAdminClient:
        if not self.client:
            raise RuntimeError("Connect to AWS first.")
        return self.client

    def refresh_collection(self, collection: str) -> None:
        def task():
            client = self.require_client()
            return collection, client.scan_all(collection)

        def done(result):
            coll, rows = result
            self.items[coll] = rows
            self.log(f"Loaded {len(rows)} {COLLECTIONS[coll]['label']} records.")
            if coll == "suggestions":
                self.populate_suggestions()
            if coll == self.record_collection_var.get():
                self.populate_records()

        self.run_background(f"Refresh {collection}", task, done)

    def refresh_selected_record_collection(self) -> None:
        self.refresh_collection(self.record_collection_var.get())

    def populate_suggestions(self) -> None:
        for row in self.suggestions_tree.get_children():
            self.suggestions_tree.delete(row)
        status_filter = self.status_filter_var.get()
        rows = self.items.get("suggestions", [])
        if status_filter != "all":
            rows = [item for item in rows if item.get("status", "") == status_filter]
        rows = sort_items(rows, ["submitted_at", "name"])
        for idx, item in enumerate(rows):
            self.suggestions_tree.insert(
                "",
                END,
                iid=str(idx),
                values=(
                    item.get("status", ""),
                    item.get("name", ""),
                    item.get("sport", ""),
                    item.get("suggestion_type", ""),
                    item.get("submitted_at", ""),
                ),
            )
        self._visible_suggestions = rows
        self.selected_suggestion = None
        self.suggestion_detail.delete("1.0", END)

    def on_suggestion_select(self, _event=None) -> None:
        sel = self.suggestions_tree.selection()
        if not sel:
            return
        item = self._visible_suggestions[int(sel[0])]
        self.selected_suggestion = item
        self.suggestion_detail.delete("1.0", END)
        self.suggestion_detail.insert("1.0", json.dumps(item, cls=JsonDecimalEncoder, indent=2, sort_keys=True))

    def suggestion_or_raise(self) -> dict:
        if not self.selected_suggestion:
            raise RuntimeError("Select a suggestion first.")
        return self.selected_suggestion

    def open_suggestion_url(self) -> None:
        try:
            item = self.suggestion_or_raise()
            url = item.get("official_url") or item.get("source_url")
            if not url:
                raise RuntimeError("Selected suggestion has no URL.")
            webbrowser.open(str(url))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def open_record_url(self) -> None:
        try:
            item = self.record_or_raise()
            url = item.get("official_url") or item.get("source_url")
            if not url:
                raise RuntimeError("Selected record has no official/source URL.")
            webbrowser.open(str(url))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def build_sport_body_from_suggestion(self, suggestion: dict) -> dict:
        name = str(suggestion.get("name", "")).strip()
        sport = str(suggestion.get("sport", "")).strip() or "Sport"
        note = str(suggestion.get("submitter_note", "")).strip()
        return {
            "id": slugify(name, "body-"),
            "name": name,
            "sport": sport,
            "level": "Community-suggested official body",
            "region": str(suggestion.get("region", "")).strip() or "To verify",
            "summary": note or f"Community-suggested official body or participation pathway for {sport}.",
            "participation_note": "Review and verify this entry before relying on it as an official pathway.",
            "tags": [tag for tag in [sport.lower(), "community suggestion", "pending verification"] if tag],
            "official_url": str(suggestion.get("official_url", "")).strip(),
            "cta_label": "Visit official site",
            "source_name": "Community suggestion",
            "last_verified": today_iso_date(),
            "created_from_suggestion_id": suggestion.get("id"),
            "status": "approved",
        }

    def build_pathway_from_suggestion(self, suggestion: dict) -> dict:
        name = str(suggestion.get("name", "")).strip()
        sport = str(suggestion.get("sport", "")).strip() or "Sport"
        note = str(suggestion.get("submitter_note", "")).strip()
        return {
            "id": slugify(name, "participation-"),
            "name": f"{name} pathway",
            "sport": sport,
            "nationality": str(suggestion.get("region", "")).strip() or "Local / regional",
            "rank_label": "Participation pathway",
            "tournament_ids": [],
            "feature_reason": f"Community-suggested pathway for people interested in {sport}.",
            "bio": note or f"Use the linked organisation as a starting point for clubs, programs, volunteering, coaching or officiating in {sport}.",
            "career_stats": {
                "pathways": "clubs, programs, volunteering, coaching, officiating",
                "accessibility": "verify with the organisation or local club",
            },
            "accomplishments": ["Community-suggested pathway awaiting editorial verification"],
            "source_name": "Community suggestion",
            "source_url": str(suggestion.get("official_url", "")).strip(),
            "last_verified": today_iso_date(),
            "created_from_suggestion_id": suggestion.get("id"),
            "status": "approved",
        }

    def approve_suggestion_as_body(self) -> None:
        try:
            suggestion = self.suggestion_or_raise()
            initial = self.build_sport_body_from_suggestion(suggestion)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        def save(payload: dict) -> None:
            client = self.require_client()
            client.put_item("sport_bodies", payload)
            client.update_suggestion_status(
                suggestion["id"],
                "approved",
                {"approved_collection": "sport_bodies", "approved_item_id": payload["id"]},
            )
            self.refresh_after_approval("sport_bodies")

        JsonEditor(self.root, "Approve suggestion as official body", initial, save)

    def approve_suggestion_as_pathway(self) -> None:
        try:
            suggestion = self.suggestion_or_raise()
            initial = self.build_pathway_from_suggestion(suggestion)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        def save(payload: dict) -> None:
            client = self.require_client()
            client.put_item("pathways", payload)
            client.update_suggestion_status(
                suggestion["id"],
                "approved",
                {"approved_collection": "pathways", "approved_item_id": payload["id"]},
            )
            self.refresh_after_approval("pathways")

        JsonEditor(self.root, "Approve suggestion as pathway", initial, save)

    def refresh_after_approval(self, collection: str) -> None:
        self.log(f"Approved suggestion into {collection}.")
        self.refresh_collection("suggestions")
        self.refresh_collection(collection)

    def reject_suggestion(self) -> None:
        try:
            suggestion = self.suggestion_or_raise()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not messagebox.askyesno(APP_TITLE, f"Reject suggestion '{suggestion.get('name')}'?"):
            return

        def task():
            self.require_client().update_suggestion_status(suggestion["id"], "rejected")
            return None

        def done(_):
            self.log("Suggestion rejected.")
            self.refresh_collection("suggestions")

        self.run_background("Reject suggestion", task, done)

    def delete_suggestion(self) -> None:
        try:
            suggestion = self.suggestion_or_raise()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not messagebox.askyesno(APP_TITLE, f"Delete suggestion '{suggestion.get('name')}' permanently?"):
            return

        def task():
            self.require_client().delete_item("suggestions", suggestion["id"])
            return None

        def done(_):
            self.log("Suggestion deleted.")
            self.refresh_collection("suggestions")

        self.run_background("Delete suggestion", task, done)

    def populate_records(self) -> None:
        for row in self.records_tree.get_children():
            self.records_tree.delete(row)
        collection = self.record_collection_var.get()
        rows = self.items.get(collection, [])
        needle = self.record_search_var.get().strip().lower()
        if needle:
            rows = [item for item in rows if needle in json.dumps(item, cls=JsonDecimalEncoder).lower()]
        rows = sort_items(rows, COLLECTIONS[collection]["sort"])
        for idx, item in enumerate(rows):
            self.records_tree.insert(
                "",
                END,
                iid=str(idx),
                values=(
                    item.get("id", ""),
                    get_text_preview(item, "name", "title"),
                    item.get("sport", ""),
                    item.get("updated_at", ""),
                ),
            )
        self._visible_records = rows
        self.selected_record = None
        self.record_detail.delete("1.0", END)

    def on_record_select(self, _event=None) -> None:
        sel = self.records_tree.selection()
        if not sel:
            return
        item = self._visible_records[int(sel[0])]
        self.selected_record = item
        self.record_detail.delete("1.0", END)
        self.record_detail.insert("1.0", json.dumps(item, cls=JsonDecimalEncoder, indent=2, sort_keys=True))

    def record_or_raise(self) -> dict:
        if not self.selected_record:
            raise RuntimeError("Select a record first.")
        return self.selected_record

    def new_record_template(self, collection: str) -> dict:
        base = {
            "id": "new-record-id",
            "name": "New record",
            "sport": "",
            "summary": "",
            "tags": [],
            "last_verified": today_iso_date(),
            "status": "approved",
        }
        if collection == "sport_bodies":
            base.update({"level": "", "region": "Australia", "official_url": "", "cta_label": "Visit official site"})
        elif collection == "top_players":
            base.update({"genre": "", "country": "Australia", "rank_label": "", "why_featured": "", "achievements": [], "stats_note": "", "official_url": "", "related_body_ids": []})
        elif collection == "pathways":
            base.update({"nationality": "", "rank_label": "Participation pathway", "bio": "", "career_stats": {}, "accomplishments": [], "source_url": ""})
        elif collection == "tournaments":
            base.update({"start_date": today_iso_date(), "end_date": today_iso_date(), "hosts": [], "source_url": ""})
        elif collection == "events":
            base.update({"tournament_id": "", "date": today_iso_date(), "venue": "", "source_url": ""})
        return base

    def new_record(self) -> None:
        collection = self.record_collection_var.get()
        initial = self.new_record_template(collection)

        def save(payload: dict) -> None:
            self.require_client().put_item(collection, payload)
            self.log(f"Saved new {collection} record: {payload['id']}")
            self.refresh_collection(collection)

        JsonEditor(self.root, f"New {COLLECTIONS[collection]['label']} record", initial, save)

    def edit_selected_record(self) -> None:
        try:
            collection = self.record_collection_var.get()
            item = deepcopy(self.record_or_raise())
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        def save(payload: dict) -> None:
            self.require_client().put_item(collection, payload)
            self.log(f"Saved {collection} record: {payload['id']}")
            self.refresh_collection(collection)

        JsonEditor(self.root, f"Edit {item.get('id')}", item, save)

    def delete_selected_record(self) -> None:
        try:
            collection = self.record_collection_var.get()
            item = self.record_or_raise()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not messagebox.askyesno(APP_TITLE, f"Delete {collection} record '{item.get('id')}' permanently?"):
            return

        def task():
            self.require_client().delete_item(collection, item["id"])
            return None

        def done(_):
            self.log(f"Deleted {collection} record: {item['id']}")
            self.refresh_collection(collection)

        self.run_background("Delete record", task, done)

    def export_all(self) -> None:
        if not self.client:
            messagebox.showerror(APP_TITLE, "Connect to AWS first.")
            return
        default = Path.home() / "Downloads" / f"sports-admin-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path = filedialog.asksaveasfilename(
            title="Export DynamoDB catalogue",
            initialfile=default.name,
            initialdir=str(default.parent),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        def task():
            client = self.require_client()
            data = {collection: client.scan_all(collection) for collection in COLLECTIONS}
            Path(path).write_text(json.dumps(data, cls=JsonDecimalEncoder, indent=2, sort_keys=True), encoding="utf-8")
            return path

        def done(saved_path):
            self.log(f"Exported catalogue to {saved_path}")

        self.run_background("Export all tables", task, done)

    def import_json(self) -> None:
        if not self.client:
            messagebox.showerror(APP_TITLE, "Connect to AWS first.")
            return
        path = filedialog.askopenfilename(
            title="Import catalogue JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(APP_TITLE, "Import will upsert records by id into DynamoDB. Continue?"):
            return

        def task():
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Import file must be a JSON object keyed by collection name.")
            client = self.require_client()
            counts: dict[str, int] = {}
            for collection, rows in payload.items():
                if collection not in COLLECTIONS:
                    continue
                if not isinstance(rows, list):
                    raise ValueError(f"Collection {collection} must be a list.")
                count = 0
                for item in rows:
                    if not isinstance(item, dict) or not item.get("id"):
                        raise ValueError(f"Invalid item in {collection}; every item must be an object with id.")
                    client.put_item(collection, item)
                    count += 1
                counts[collection] = count
            refreshed = {collection: client.scan_all(collection) for collection in COLLECTIONS}
            return counts, refreshed

        def done(result):
            counts, refreshed = result
            self.items = refreshed
            self.populate_suggestions()
            self.populate_records()
            self.log("Imported records: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

        self.run_background("Import JSON", task, done)


def main() -> None:
    root = Tk()
    try:
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    SportsAdminApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
