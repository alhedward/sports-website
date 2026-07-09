#!/usr/bin/env python3
"""
Sports.vk2ale Local Admin Manager

A Tkinter tool for administering the Sports.vk2ale catalogue.

Default mode uses Cognito hosted login plus the protected admin API, so delegated
admins do not need AWS credentials. A boto3 direct mode remains available as an
owner/emergency fallback while the project is in development.

Run:
  python3 sports/admin_manager/sports_admin_manager.py

Optional:
  AWS_PROFILE=my-profile python3 sports/admin_manager/sports_admin_manager.py
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import http.server
import json
import os
import re
import secrets
import socket
import socketserver
import threading
import time
import uuid
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, TOP, BOTTOM, X, Y, BooleanVar, StringVar, Text, Tk, Toplevel, Menu, filedialog, messagebox
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
DEFAULT_AUTH_MODE = os.environ.get("SPORTS_ADMIN_AUTH_MODE", "cognito_api")
DEFAULT_ADMIN_API_URL = os.environ.get("SPORTS_ADMIN_API_URL", "")
DEFAULT_COGNITO_DOMAIN = os.environ.get("SPORTS_ADMIN_COGNITO_DOMAIN", "")
DEFAULT_COGNITO_CLIENT_ID = os.environ.get("SPORTS_ADMIN_COGNITO_CLIENT_ID", "")
DEFAULT_CALLBACK_PORT = os.environ.get("SPORTS_ADMIN_CALLBACK_PORT", "8765")
LOCAL_CONFIG_PATH = Path.home() / ".sports-vk2ale-admin-manager.json"


def load_local_config() -> dict:
    """Load small local UI config from the user's home directory."""
    try:
        if LOCAL_CONFIG_PATH.exists():
            data = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        # Do not prevent the admin app from starting because a local preferences
        # file is missing, corrupt, or temporarily unreadable.
        pass
    return {}


LOCAL_CONFIG = load_local_config()
DEFAULT_ADMIN_API_URL = os.environ.get("SPORTS_ADMIN_API_URL", LOCAL_CONFIG.get("admin_api_url", DEFAULT_ADMIN_API_URL))
DEFAULT_COGNITO_DOMAIN = os.environ.get("SPORTS_ADMIN_COGNITO_DOMAIN", LOCAL_CONFIG.get("cognito_domain", DEFAULT_COGNITO_DOMAIN))
DEFAULT_COGNITO_CLIENT_ID = os.environ.get("SPORTS_ADMIN_COGNITO_CLIENT_ID", LOCAL_CONFIG.get("cognito_client_id", DEFAULT_COGNITO_CLIENT_ID))
APP_VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
ACTIVITY_LOG_COLLECTION = "activity_log"
ACTIVITY_LOG_SUFFIX = "activity-log"
ACTIVITY_LOG_DISPLAY_LIMIT = 500


APP_AUTHOR = "Tony Edward / VK2ALE"
APP_SUPPORT = "OpenAI ChatGPT coding support"
APP_VERSION_FALLBACK = "0.7.7-admin-menu-cognito-users"


def read_app_version() -> str:
    """Read the package version, with a standalone-admin-app fallback."""
    candidates = [
        APP_VERSION_FILE,
        Path(__file__).resolve().parent / "VERSION",
        Path(__file__).resolve().parent.parent / "VERSION",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except Exception:
            pass
    return APP_VERSION_FALLBACK


def center_window(window, width: int | None = None, height: int | None = None, parent=None) -> None:
    """Centre a Tk/Toplevel window on the screen or over its parent."""
    try:
        window.update_idletasks()
        if width is None:
            width = max(window.winfo_reqwidth(), window.winfo_width())
        if height is None:
            height = max(window.winfo_reqheight(), window.winfo_height())
        if parent is not None:
            parent.update_idletasks()
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_w = parent.winfo_width()
            parent_h = parent.winfo_height()
            x = parent_x + max((parent_w - width) // 2, 0)
            y = parent_y + max((parent_h - height) // 2, 0)
        else:
            screen_w = window.winfo_screenwidth()
            screen_h = window.winfo_screenheight()
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
        window.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        if width and height:
            window.geometry(f"{width}x{height}")

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
        if collection == ACTIVITY_LOG_COLLECTION:
            suffix = ACTIVITY_LOG_SUFFIX
        else:
            suffix = COLLECTIONS[collection]["suffix"]
        return f"{self.prefix}-{suffix}"

    @property
    def activity_log_table_name(self) -> str:
        return self.table_name(ACTIVITY_LOG_COLLECTION)


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

    def activity_table(self):
        return self.ddb.Table(self.config.activity_log_table_name)

    def scan_activity_log(self, limit: int = ACTIVITY_LOG_DISPLAY_LIMIT) -> list[dict]:
        items: list[dict] = []
        kwargs: dict = {}
        table = self.activity_table()
        while True:
            response = table.scan(**kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return items[:limit]

    def write_activity(
        self,
        action: str,
        summary: str,
        *,
        details: dict | None = None,
        actor_arn: str | None = None,
    ) -> dict:
        created_at = now_iso()
        actor = actor_arn or ""
        try:
            if not actor:
                actor = self.caller_identity().get("Arn", "")
        except Exception:
            actor = ""
        version = read_app_version()
        item = {
            "id": f"log-{created_at.replace(':', '').replace('.', '-')}-{uuid.uuid4().hex[:10]}",
            "created_at": created_at,
            "action": action,
            "summary": summary,
            "actor_arn": actor,
            "aws_profile": self.config.profile or "default",
            "aws_region": self.config.region,
            "project_name": self.config.project_name,
            "environment": self.config.environment,
            "host": socket.gethostname(),
            "local_user": getpass.getuser(),
            "app_version": version,
        }
        if details:
            item["details"] = details
        self.activity_table().put_item(Item=normalize_decimal(item))
        return item

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


@dataclass
class CognitoApiConfig:
    api_base_url: str
    cognito_domain: str
    client_id: str
    callback_port: int = 8765

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.callback_port}/callback"


def _b64url_no_padding(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_jwt_unverified(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


def _claim_groups(claims: dict) -> list[str]:
    raw = claims.get("cognito:groups") or claims.get("groups") or claims.get("cognito_groups")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip().strip("'\"") for item in raw if str(item).strip()]
    value = str(raw).strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(item).strip().strip("'\"") for item in decoded if str(item).strip()]
        except Exception:
            value = inner
    return [part.strip().strip("'\"") for part in value.split(",") if part.strip().strip("'\"")]


def _token_debug_summary(tokens: dict) -> str:
    parts = []
    for name in ("id_token", "access_token"):
        claims = _decode_jwt_unverified(tokens.get(name, ""))
        if not claims:
            parts.append(f"{name}=missing")
            continue
        groups = _claim_groups(claims)
        token_use = claims.get("token_use", "?")
        aud = claims.get("aud") or claims.get("client_id") or "?"
        parts.append(f"{name}: use={token_use}, aud/client={aud}, groups={groups or 'none'}")
    return "; ".join(parts)


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    server_version = "SportsAdminOAuthCallback/1.0"

    def log_message(self, fmt, *args):  # keep Tkinter console clean
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        self.server.auth_code = (params.get("code") or [""])[0]
        self.server.auth_state = (params.get("state") or [""])[0]
        self.server.auth_error = (params.get("error") or [""])[0]
        self.server.auth_error_description = (params.get("error_description") or [""])[0]
        body = b"<html><body><h1>Sports admin login complete</h1><p>You can close this browser tab and return to the admin manager.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CognitoPkceAuth:
    def __init__(self, config: CognitoApiConfig) -> None:
        self.config = config
        self.tokens: dict = {}
        self.claims: dict = {}
        # API Gateway HTTP API JWT authorizers normally accept Cognito access tokens
        # because their audience validation checks the access token client_id claim.
        # Keep this mutable so we can fall back to the ID token and show diagnostics
        # when a deployment is configured differently.
        self.preferred_token_name = "access_token"

    @property
    def domain(self) -> str:
        value = self.config.cognito_domain.strip().rstrip("/")
        if not value:
            raise RuntimeError("Cognito domain is required for Cognito API mode.")
        if not value.startswith(("https://", "http://")):
            value = "https://" + value
        return value

    def login(self, timeout_seconds: int = 180) -> dict:
        if not self.config.client_id.strip():
            raise RuntimeError("Cognito app client ID is required for Cognito API mode.")
        verifier = _b64url_no_padding(secrets.token_bytes(48))
        challenge = _b64url_no_padding(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(24)
        params = {
            "client_id": self.config.client_id.strip(),
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": self.config.redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = self.domain + "/oauth2/authorize?" + urllib.parse.urlencode(params)

        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        with ReusableTCPServer(("127.0.0.1", self.config.callback_port), _OAuthCallbackHandler) as server:
            server.auth_code = ""
            server.auth_state = ""
            server.auth_error = ""
            server.auth_error_description = ""
            server.timeout = 1
            webbrowser.open(auth_url)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline and not (server.auth_code or server.auth_error):
                server.handle_request()
            if server.auth_error:
                raise RuntimeError(f"Cognito login failed: {server.auth_error} {server.auth_error_description}")
            if not server.auth_code:
                raise RuntimeError("Timed out waiting for Cognito login callback.")
            if server.auth_state != state:
                raise RuntimeError("Cognito login state mismatch. Authentication aborted.")
            self.tokens = self.exchange_code(server.auth_code, verifier)
            self.claims = _decode_jwt_unverified(self.tokens.get("id_token") or self.tokens.get("access_token") or "")
            return self.tokens

    def exchange_code(self, code: str, verifier: str) -> dict:
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "client_id": self.config.client_id.strip(),
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "code_verifier": verifier,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.domain + "/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Token exchange failed: HTTP {exc.code}: {detail}") from exc

    def authorization_header(self) -> str:
        token = self.tokens.get(self.preferred_token_name) or self.tokens.get("id_token") or self.tokens.get("access_token")
        if not token:
            self.login()
            token = self.tokens.get(self.preferred_token_name) or self.tokens.get("id_token") or self.tokens.get("access_token")
        return f"Bearer {token}"

    def switch_to_alternate_token(self) -> bool:
        """Switch between ID and access token once when an API rejects auth."""
        alternate = "access_token" if self.preferred_token_name == "id_token" else "id_token"
        if self.tokens.get(alternate):
            self.preferred_token_name = alternate
            self.claims = _decode_jwt_unverified(self.tokens.get(alternate, ""))
            return True
        return False

    def debug_summary(self) -> str:
        return _token_debug_summary(self.tokens)


class ApiAdminClient:
    """Admin client that uses Cognito tokens and the protected /admin API."""

    def __init__(self, config: CognitoApiConfig) -> None:
        if not config.api_base_url.strip():
            raise RuntimeError("Admin API base URL is required for Cognito API mode.")
        self.config = config
        self.auth = CognitoPkceAuth(config)
        self.auth.login()
        self.api_base_url = config.api_base_url.strip().rstrip("/")

    def request(self, method: str, path: str, payload: dict | None = None, *, _retried_alt_token: bool = False):
        url = self.api_base_url + path
        data = None
        headers = {
            "Authorization": self.auth.authorization_header(),
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, cls=JsonDecimalEncoder).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                message = parsed.get("message") or detail
            except Exception:
                message = detail

            if exc.code in (401, 403) and not _retried_alt_token and self.auth.switch_to_alternate_token():
                return self.request(method, path, payload, _retried_alt_token=True)

            debug = self.auth.debug_summary()
            raise RuntimeError(f"Admin API {method} {path} failed: HTTP {exc.code}: {message}. Local token check: {debug}") from exc

    def caller_identity(self) -> dict:
        result = self.request("GET", "/admin/me")
        actor = result.get("actor", {}) if isinstance(result, dict) else {}
        name = actor.get("email") or actor.get("username") or actor.get("sub") or "cognito-admin"
        return {"Arn": f"cognito:{name}", "Actor": actor}

    def scan_all(self, collection: str) -> list[dict]:
        return self.request("GET", f"/admin/collections/{urllib.parse.quote(collection)}") or []

    def get_item(self, collection: str, item_id: str) -> dict | None:
        return self.request("GET", f"/admin/collections/{urllib.parse.quote(collection)}/{urllib.parse.quote(item_id)}")

    def put_item(self, collection: str, item: dict) -> None:
        if not item.get("id"):
            raise ValueError("Item must contain an id")
        self.request("PUT", f"/admin/collections/{urllib.parse.quote(collection)}/{urllib.parse.quote(str(item['id']))}", item)

    def delete_item(self, collection: str, item_id: str) -> None:
        self.request("DELETE", f"/admin/collections/{urllib.parse.quote(collection)}/{urllib.parse.quote(item_id)}")

    def scan_activity_log(self, limit: int = ACTIVITY_LOG_DISPLAY_LIMIT) -> list[dict]:
        return self.request("GET", f"/admin/activity-log?limit={int(limit)}") or []

    def write_activity(
        self,
        action: str,
        summary: str,
        *,
        details: dict | None = None,
        actor_arn: str | None = None,
    ) -> dict:
        return self.request("POST", "/admin/activity-log", {
            "action": action,
            "summary": summary,
            "details": details or {},
        })

    def update_suggestion_status(self, suggestion_id: str, status: str, extra: dict | None = None) -> None:
        self.request("POST", f"/admin/suggestions/{urllib.parse.quote(suggestion_id)}/status", {
            "status": status,
            "extra": extra or {},
        })


class JsonEditor(Toplevel):
    def __init__(self, parent: Tk, title: str, initial: dict, on_save) -> None:
        super().__init__(parent)
        self.title(title)
        center_window(self, 920, 720, parent)
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
        center_window(self.root, 1260, 820)
        self.client: DynamoAdminClient | None = None
        self.items: dict[str, list[dict]] = {key: [] for key in COLLECTIONS}
        self.selected_suggestion: dict | None = None
        self.selected_record: dict | None = None
        self.activity_items: list[dict] = []
        self.selected_activity: dict | None = None
        self.actor_arn = ""

        self.profile_var = StringVar(value=DEFAULT_PROFILE)
        self.region_var = StringVar(value=DEFAULT_REGION)
        self.project_var = StringVar(value=DEFAULT_PROJECT)
        self.env_var = StringVar(value=DEFAULT_ENV)
        self.auth_mode_var = StringVar(value=DEFAULT_AUTH_MODE)
        self.api_url_var = StringVar(value=DEFAULT_ADMIN_API_URL)
        self.cognito_domain_var = StringVar(value=DEFAULT_COGNITO_DOMAIN)
        self.cognito_client_id_var = StringVar(value=DEFAULT_COGNITO_CLIENT_ID)
        self.cognito_user_pool_id_var = StringVar(value=LOCAL_CONFIG.get("cognito_user_pool_id", ""))
        self.callback_port_var = StringVar(value=LOCAL_CONFIG.get("callback_port", DEFAULT_CALLBACK_PORT))
        self.connection_summary_var = StringVar(value=self.connection_summary_text())
        self.status_filter_var = StringVar(value="pending_review")
        self.record_collection_var = StringVar(value="sport_bodies")
        self.record_search_var = StringVar(value="")
        self.include_all_suggestions_var = BooleanVar(value=False)
        self.status_var = StringVar(value="Not connected.")
        self._local_config_save_job = None

        self.build_menu()
        self.build_ui()
        self.install_local_config_autosave()
        self.auth_mode_var.trace_add("write", lambda *_args: self.update_menu_state())
        self.update_menu_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_menu(self) -> None:
        menu_bar = Menu(self.root)

        file_menu = Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Login / connect", command=self.connect_and_refresh)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        admin_menu = Menu(menu_bar, tearoff=0)
        admin_menu.add_command(label="API / Cognito settings...", command=self.open_connection_settings_modal)
        admin_menu.add_command(label="Add Cognito user...", command=self.open_add_cognito_user_modal)
        menu_bar.add_cascade(label="Admin", menu=admin_menu)
        self.admin_menu = admin_menu
        self.add_user_menu_index = 1

        help_menu = Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="About", command=self.open_about_modal)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menu_bar)

    def connection_summary_text(self) -> str:
        api_state = "set" if self.api_url_var.get().strip() else "missing"
        domain_state = "set" if self.cognito_domain_var.get().strip() else "missing"
        client_state = "set" if self.cognito_client_id_var.get().strip() else "missing"
        return f"API/Cognito settings: Admin API {api_state}, Cognito domain {domain_state}, Client ID {client_state}. Edit from Admin → API / Cognito settings."

    def refresh_connection_summary(self) -> None:
        if hasattr(self, "connection_summary_var"):
            self.connection_summary_var.set(self.connection_summary_text())

    def update_menu_state(self) -> None:
        mode = self.auth_mode_var.get().strip() or "cognito_api"
        try:
            state = "normal" if mode == "boto3_direct" else "disabled"
            self.admin_menu.entryconfig(self.add_user_menu_index, state=state)
        except Exception:
            pass
        self.refresh_connection_summary()

    def open_about_modal(self) -> None:
        version = read_app_version()
        message = (
            f"{APP_TITLE}\n\n"
            f"Version: {version}\n"
            f"Project owner / author: {APP_AUTHOR}\n"
            f"Development support: {APP_SUPPORT}\n\n"
            "Sports.vk2ale community sports catalogue administration tool."
        )
        messagebox.showinfo("About", message, parent=self.root)

    def open_connection_settings_modal(self) -> None:
        win = Toplevel(self.root)
        win.title("API / Cognito settings")
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="Admin API").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.api_url_var, width=72).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Cognito domain").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.cognito_domain_var, width=72).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Client ID").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.cognito_client_id_var, width=72).grid(row=2, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Callback port").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.callback_port_var, width=12).grid(row=3, column=1, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Cognito user pool ID").grid(row=4, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.cognito_user_pool_id_var, width=34).grid(row=4, column=1, sticky="w", pady=(0, 8))

        note = (
            "These settings are saved automatically to "
            f"{LOCAL_CONFIG_PATH}.\n"
            "Use Discover while in boto3_direct/owner mode to populate them from AWS."
        )
        ttk.Label(frame, text=note, wraplength=640).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 12))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Discover via boto3", command=self.discover_settings_from_modal).pack(side=LEFT)
        ttk.Button(buttons, text="Close", command=lambda: (self.save_local_config(), win.destroy())).pack(side=RIGHT)

        frame.columnconfigure(1, weight=1)
        center_window(win, 760, 300, self.root)
        win.protocol("WM_DELETE_WINDOW", lambda: (self.save_local_config(), win.destroy()))

    def discover_settings_from_modal(self) -> None:
        def task():
            return self.discover_connection_fields_via_boto3(self.get_config())

        def done(discovered: dict):
            self.apply_discovered_connection_fields(discovered)
            for message in discovered.get("messages", []):
                self.log(message)
            self.log("Discovery complete.")

        self.run_background("Discover API/Cognito settings", task, done)

    def open_add_cognito_user_modal(self) -> None:
        if (self.auth_mode_var.get().strip() or "cognito_api") != "boto3_direct":
            messagebox.showinfo(
                APP_TITLE,
                "Add Cognito user is owner/bootstrap only and is available in boto3_direct mode, not cognito_api mode.",
                parent=self.root,
            )
            return

        win = Toplevel(self.root)
        win.title("Add Cognito user")
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill=BOTH, expand=True)

        email_var = StringVar(value="")
        role_var = StringVar(value="Admins")
        send_email_var = BooleanVar(value=True)

        ttk.Label(frame, text="Email / username").grid(row=0, column=0, sticky="w", pady=(0, 8))
        email_entry = ttk.Entry(frame, textvariable=email_var, width=46)
        email_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Role").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(
            frame,
            textvariable=role_var,
            values=["PrimaryAdmins", "Admins", "Editors"],
            state="readonly",
            width=24,
        ).grid(row=1, column=1, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="User pool ID").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.cognito_user_pool_id_var, width=34).grid(row=2, column=1, sticky="w", pady=(0, 8))
        ttk.Checkbutton(frame, text="Send Cognito welcome email", variable=send_email_var).grid(row=3, column=1, sticky="w", pady=(0, 8))
        ttk.Label(
            frame,
            text="This uses your local AWS/boto3 credentials. Keep it as an owner/bootstrap control only.",
            wraplength=520,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 12))

        def create_clicked():
            email = email_var.get().strip()
            group = role_var.get().strip()
            send_email = bool(send_email_var.get())
            if not email or "@" not in email:
                messagebox.showerror(APP_TITLE, "Enter a valid email address.", parent=win)
                return
            if group not in {"PrimaryAdmins", "Admins", "Editors"}:
                messagebox.showerror(APP_TITLE, "Choose a valid role.", parent=win)
                return

            def task():
                return self.create_cognito_user_via_boto3(email, group, send_email)

            def done(result: dict):
                self.log(result.get("message", "Cognito user created."))
                messagebox.showinfo(APP_TITLE, result.get("message", "Cognito user created."), parent=win)
                win.destroy()

            self.run_background("Create Cognito user", task, done)

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Discover user pool", command=self.discover_settings_from_modal).pack(side=LEFT)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side=RIGHT)
        ttk.Button(buttons, text="Create user", command=create_clicked).pack(side=RIGHT, padx=(0, 10))

        frame.columnconfigure(1, weight=1)
        center_window(win, 620, 300, self.root)
        email_entry.focus_set()

    def create_cognito_user_via_boto3(self, email: str, group: str, send_welcome_email: bool) -> dict:
        if boto3 is None:
            raise RuntimeError("boto3 is not installed. Run: python3 -m pip install boto3")
        config = self.get_config()
        user_pool_id = self.cognito_user_pool_id_var.get().strip()
        if not user_pool_id:
            discovered = self.discover_connection_fields_via_boto3(config)
            self.root.after(0, lambda cfg=deepcopy(discovered): self.apply_discovered_connection_fields(cfg))
            user_pool_id = str(discovered.get("cognito_user_pool_id") or "").strip()
        if not user_pool_id:
            raise RuntimeError("Could not determine Cognito user pool ID. Use Admin → API / Cognito settings → Discover via boto3 first.")

        if config.profile:
            session = boto3.Session(profile_name=config.profile, region_name=config.region)
        else:
            session = boto3.Session(region_name=config.region)
        cognito = session.client("cognito-idp")

        kwargs = {
            "UserPoolId": user_pool_id,
            "Username": email,
            "UserAttributes": [
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            "DesiredDeliveryMediums": ["EMAIL"],
        }
        if not send_welcome_email:
            kwargs["MessageAction"] = "SUPPRESS"

        created = False
        try:
            cognito.admin_create_user(**kwargs)
            created = True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "UsernameExistsException":
                raise
        cognito.admin_add_user_to_group(UserPoolId=user_pool_id, Username=email, GroupName=group)

        summary = f"Cognito user {'created and ' if created else ''}added to {group}: {email}"
        try:
            if self.client:
                self.client.write_activity(
                    "cognito_user_created" if created else "cognito_user_group_added",
                    summary,
                    actor_arn=self.actor_arn,
                    details={
                        "email": email,
                        "group": group,
                        "user_pool_id": user_pool_id,
                        "sent_welcome_email": send_welcome_email,
                        "created": created,
                    },
                )
        except Exception as exc:
            summary += f". Activity log write failed: {exc}"
        return {"message": summary, "created": created, "user_pool_id": user_pool_id, "group": group, "email": email}

    def build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=TOP, fill=X)
        ttk.Label(top, text="Mode").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            top,
            textvariable=self.auth_mode_var,
            values=["cognito_api", "boto3_direct"],
            width=14,
            state="readonly",
        ).grid(row=0, column=1, padx=(4, 12), sticky="w")
        ttk.Label(top, text="AWS profile").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.profile_var, width=14).grid(row=0, column=3, padx=(4, 12), sticky="w")
        ttk.Label(top, text="Region").grid(row=0, column=4, sticky="w")
        ttk.Entry(top, textvariable=self.region_var, width=16).grid(row=0, column=5, padx=(4, 12), sticky="w")
        ttk.Label(top, text="Project").grid(row=0, column=6, sticky="w")
        ttk.Entry(top, textvariable=self.project_var, width=18).grid(row=0, column=7, padx=(4, 12), sticky="w")
        ttk.Label(top, text="Env").grid(row=0, column=8, sticky="w")
        ttk.Entry(top, textvariable=self.env_var, width=8).grid(row=0, column=9, padx=(4, 12), sticky="w")
        ttk.Button(top, text="Login / connect", command=self.connect_and_refresh).grid(row=0, column=10, sticky="e")
        ttk.Label(top, textvariable=self.connection_summary_var).grid(row=1, column=0, columnspan=11, sticky="w", pady=(8, 0))
        top.columnconfigure(7, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))
        self.build_suggestions_tab()
        self.build_records_tab()
        self.build_activity_tab()
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

    def build_activity_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Activity log")

        info = (
            "Shared site-side activity log stored in DynamoDB. "
            "This is not shown on the public website; it is only read by local admin apps."
        )
        ttk.Label(tab, text=info, wraplength=980, justify="left").pack(anchor="w")

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X, pady=(10, 8))
        ttk.Button(toolbar, text="Refresh shared log", command=self.refresh_activity_log).pack(side=LEFT)
        ttk.Button(toolbar, text="Export activity log", command=self.export_activity_log).pack(side=LEFT, padx=(8, 0))

        main = ttk.Panedwindow(tab, orient="horizontal")
        main.pack(fill=BOTH, expand=True)

        left = ttk.Frame(main)
        main.add(left, weight=3)
        columns = ("created_at", "action", "actor", "summary")
        self.activity_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for col, label, width in [
            ("created_at", "UTC time", 210),
            ("action", "Action", 170),
            ("actor", "Actor", 330),
            ("summary", "Summary", 360),
        ]:
            self.activity_tree.heading(col, text=label)
            self.activity_tree.column(col, width=width, anchor="w")
        self.activity_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.activity_tree.bind("<<TreeviewSelect>>", self.on_activity_select)
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.activity_tree.yview)
        yscroll.pack(side=RIGHT, fill=Y)
        self.activity_tree.configure(yscrollcommand=yscroll.set)

        right = ttk.Frame(main)
        main.add(right, weight=2)
        ttk.Label(right, text="Activity detail").pack(anchor="w")
        self.activity_detail = Text(right, height=18, wrap="word")
        self.activity_detail.pack(fill=BOTH, expand=True, pady=(6, 0))

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

        ttk.Label(tab, text="Local session status / errors").pack(anchor="w", pady=(10, 4))
        self.log_text = Text(tab, height=24, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}\n"
        if hasattr(self, "log_text"):
            self.log_text.insert(END, line)
            self.log_text.see(END)
        self.status_var.set(message)

    def install_local_config_autosave(self) -> None:
        """Automatically persist Cognito/API connection fields as the user edits them."""
        for var in (self.api_url_var, self.cognito_domain_var, self.cognito_client_id_var, self.callback_port_var, self.cognito_user_pool_id_var):
            var.trace_add("write", lambda *_args: (self.refresh_connection_summary(), self.schedule_local_config_save()))

    def schedule_local_config_save(self) -> None:
        """Debounce local config writes so typing/pasting does not hammer the disk."""
        if self._local_config_save_job is not None:
            try:
                self.root.after_cancel(self._local_config_save_job)
            except Exception:
                pass
        self._local_config_save_job = self.root.after(400, self.save_local_config)

    def save_local_config(self) -> None:
        """Write the three Cognito/API fields to a JSON file in the user's home directory."""
        self._local_config_save_job = None
        data = load_local_config()
        data.update({
            "admin_api_url": self.api_url_var.get().strip(),
            "cognito_domain": self.cognito_domain_var.get().strip(),
            "cognito_client_id": self.cognito_client_id_var.get().strip(),
            "cognito_user_pool_id": self.cognito_user_pool_id_var.get().strip(),
            "callback_port": self.callback_port_var.get().strip(),
            "updated_at": now_iso(),
        })
        try:
            tmp_path = LOCAL_CONFIG_PATH.with_suffix(LOCAL_CONFIG_PATH.suffix + ".tmp")
            tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp_path.replace(LOCAL_CONFIG_PATH)
            try:
                os.chmod(LOCAL_CONFIG_PATH, 0o600)
            except Exception:
                pass
        except Exception:
            # Saving convenience config must never interrupt an approval/edit flow.
            pass

    def on_close(self) -> None:
        """Persist local connection details before the app exits."""
        if self._local_config_save_job is not None:
            try:
                self.root.after_cancel(self._local_config_save_job)
            except Exception:
                pass
            self._local_config_save_job = None
        self.save_local_config()
        self.root.destroy()

    def get_config(self) -> AwsConfig:
        return AwsConfig(
            profile=self.profile_var.get().strip(),
            region=self.region_var.get().strip() or DEFAULT_REGION,
            project_name=self.project_var.get().strip() or DEFAULT_PROJECT,
            environment=self.env_var.get().strip() or DEFAULT_ENV,
        )

    def get_api_config(self) -> CognitoApiConfig:
        try:
            port = int(self.callback_port_var.get().strip() or DEFAULT_CALLBACK_PORT)
        except ValueError as exc:
            raise ValueError("Callback port must be a number") from exc
        return CognitoApiConfig(
            api_base_url=self.api_url_var.get().strip(),
            cognito_domain=self.cognito_domain_var.get().strip(),
            client_id=self.cognito_client_id_var.get().strip(),
            callback_port=port,
        )

    def discover_connection_fields_via_boto3(self, config: AwsConfig) -> dict:
        """Discover Cognito/API connection fields using the selected boto3 profile.

        This is a convenience for the owner/emergency boto3_direct mode: after a
        successful AWS connection, the app can fill the Cognito/API fields that
        delegated admins use later, without requiring command-line lookups.
        """
        if boto3 is None:
            raise RuntimeError("boto3 is not installed. Run: python3 -m pip install boto3")
        if config.profile:
            session = boto3.Session(profile_name=config.profile, region_name=config.region)
        else:
            session = boto3.Session(region_name=config.region)

        prefix = config.prefix
        wanted_api_name = f"{prefix}-http-api"
        wanted_pool_name = f"{prefix}-admin-users"
        wanted_client_name = f"{prefix}-admin-local-app"

        discovered = {
            "admin_api_url": "",
            "cognito_domain": "",
            "cognito_client_id": "",
            "cognito_user_pool_id": "",
            "messages": [],
        }

        # API Gateway HTTP API endpoint.
        try:
            apigw = session.client("apigatewayv2")
            apis = []
            try:
                paginator = apigw.get_paginator("get_apis")
                for page in paginator.paginate():
                    apis.extend(page.get("Items", []))
            except Exception:
                response = apigw.get_apis()
                apis.extend(response.get("Items", []))
            match = next((api for api in apis if api.get("Name") == wanted_api_name), None)
            if not match:
                candidates = [
                    api for api in apis
                    if str(api.get("Name", "")).startswith(prefix) and api.get("ApiEndpoint")
                ]
                match = next((api for api in candidates if "http" in str(api.get("Name", "")).lower()), None)
                if not match and len(candidates) == 1:
                    match = candidates[0]
            if match and match.get("ApiEndpoint"):
                discovered["admin_api_url"] = str(match["ApiEndpoint"]).rstrip("/")
                discovered["messages"].append(f"Admin API discovered: {match.get('Name', wanted_api_name)}")
            else:
                discovered["messages"].append(f"Admin API not found: {wanted_api_name}")
        except Exception as exc:
            discovered["messages"].append(f"Admin API discovery failed: {exc}")

        # Cognito user pool, hosted UI domain and local-app client ID.
        try:
            cognito = session.client("cognito-idp")
            pools = []
            kwargs = {"MaxResults": 60}
            while True:
                response = cognito.list_user_pools(**kwargs)
                pools.extend(response.get("UserPools", []))
                token = response.get("NextToken")
                if not token:
                    break
                kwargs["NextToken"] = token

            pool = next((item for item in pools if item.get("Name") == wanted_pool_name), None)
            if not pool:
                pool_candidates = [
                    item for item in pools
                    if str(item.get("Name", "")).startswith(prefix)
                    and "admin" in str(item.get("Name", "")).lower()
                ]
                if len(pool_candidates) == 1:
                    pool = pool_candidates[0]
            if not pool:
                discovered["messages"].append(f"Cognito user pool not found: {wanted_pool_name}")
                return discovered

            user_pool_id = pool.get("Id", "")
            discovered["cognito_user_pool_id"] = user_pool_id
            discovered["messages"].append(f"Cognito user pool discovered: {wanted_pool_name}")

            description = cognito.describe_user_pool(UserPoolId=user_pool_id).get("UserPool", {})
            custom_domain = description.get("CustomDomain")
            domain_prefix = description.get("Domain")
            if custom_domain:
                discovered["cognito_domain"] = f"https://{custom_domain}"
            elif domain_prefix:
                discovered["cognito_domain"] = f"https://{domain_prefix}.auth.{config.region}.amazoncognito.com"
            else:
                discovered["messages"].append("Cognito hosted-login domain not configured on the user pool.")

            clients = []
            kwargs = {"UserPoolId": user_pool_id, "MaxResults": 60}
            while True:
                response = cognito.list_user_pool_clients(**kwargs)
                clients.extend(response.get("UserPoolClients", []))
                token = response.get("NextToken")
                if not token:
                    break
                kwargs["NextToken"] = token

            app_client = next((item for item in clients if item.get("ClientName") == wanted_client_name), None)
            if not app_client:
                client_candidates = [
                    item for item in clients
                    if "admin" in str(item.get("ClientName", "")).lower()
                ]
                if len(client_candidates) == 1:
                    app_client = client_candidates[0]
                elif len(clients) == 1:
                    app_client = clients[0]
            if app_client and app_client.get("ClientId"):
                discovered["cognito_client_id"] = str(app_client["ClientId"])
                discovered["messages"].append(f"Cognito app client discovered: {app_client.get('ClientName', wanted_client_name)}")
            else:
                discovered["messages"].append(f"Cognito app client not found: {wanted_client_name}")
        except Exception as exc:
            discovered["messages"].append(f"Cognito discovery failed: {exc}")

        return discovered

    def apply_discovered_connection_fields(self, discovered: dict) -> None:
        """Populate the three Cognito/API fields and persist them locally."""
        changed = False
        value = str(discovered.get("admin_api_url") or "").strip()
        if value and value != self.api_url_var.get().strip():
            self.api_url_var.set(value)
            changed = True
        value = str(discovered.get("cognito_domain") or "").strip()
        if value and value != self.cognito_domain_var.get().strip():
            self.cognito_domain_var.set(value)
            changed = True
        value = str(discovered.get("cognito_client_id") or "").strip()
        if value and value != self.cognito_client_id_var.get().strip():
            self.cognito_client_id_var.set(value)
            changed = True
        value = str(discovered.get("cognito_user_pool_id") or "").strip()
        if value and value != self.cognito_user_pool_id_var.get().strip():
            self.cognito_user_pool_id_var.set(value)
            changed = True
        self.refresh_connection_summary()
        if changed:
            self.save_local_config()

    def run_background(self, label: str, func, on_done=None) -> None:
        self.status_var.set(f"Running: {label}…")
        def worker():
            try:
                result = func()
            except Exception as exc:
                tb = traceback.format_exc()
                self.root.after(0, lambda label=label, exc=exc, tb=tb: self.handle_error(label, exc, tb))
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
        self.save_local_config()

        def task():
            mode = self.auth_mode_var.get().strip() or "cognito_api"
            discovered_config = {}
            if mode == "boto3_direct":
                config = self.get_config()
                client = DynamoAdminClient(config)
                discovered_config = self.discover_connection_fields_via_boto3(config)
                # Populate the visible Cognito/API fields as soon as discovery succeeds.
                # This still happens even if a later DynamoDB scan/activity-log call fails.
                if any(discovered_config.get(key) for key in ("admin_api_url", "cognito_domain", "cognito_client_id")):
                    self.root.after(0, lambda cfg=deepcopy(discovered_config): self.apply_discovered_connection_fields(cfg))
                connection_details = {
                    "mode": mode,
                    "table_prefix": config.prefix,
                    "activity_log_table": config.activity_log_table_name,
                    "discovered_admin_api_url": discovered_config.get("admin_api_url", ""),
                    "discovered_cognito_domain": discovered_config.get("cognito_domain", ""),
                    "discovered_cognito_client_id": discovered_config.get("cognito_client_id", ""),
                    "discovered_cognito_user_pool_id": discovered_config.get("cognito_user_pool_id", ""),
                }
            else:
                client = ApiAdminClient(self.get_api_config())
                connection_details = {
                    "mode": mode,
                    "api_base_url": client.api_base_url,
                    "callback_port": client.config.callback_port,
                }
            identity = client.caller_identity()
            # Eagerly scan small catalogue tables for a clear connection test.
            items = {collection: client.scan_all(collection) for collection in COLLECTIONS}
            activity_error = ""
            activity_items: list[dict] = []
            try:
                client.write_activity(
                    "admin_app_started",
                    "Local admin app connected",
                    actor_arn=identity.get("Arn", ""),
                    details=connection_details,
                )
                activity_items = client.scan_activity_log()
            except Exception as exc:
                activity_error = str(exc)
            return client, identity, items, activity_items, activity_error, discovered_config

        def done(result):
            self.client, identity, self.items, self.activity_items, activity_error, discovered_config = result
            self.actor_arn = identity.get("Arn", "")
            if discovered_config:
                self.apply_discovered_connection_fields(discovered_config)
                for message in discovered_config.get("messages", []):
                    self.log(message)
            self.log(f"Connected as {self.actor_arn} using prefix {self.client.config.prefix}.")
            if activity_error:
                self.log(f"Shared activity log unavailable: {activity_error}")
            self.populate_suggestions()
            self.populate_records()
            self.populate_activity_log()

        self.run_background("Connect and refresh", task, done)

    def require_client(self) -> DynamoAdminClient:
        if not self.client:
            raise RuntimeError("Connect to AWS first.")
        return self.client

    def write_activity_safe(self, action: str, summary: str, details: dict | None = None) -> None:
        """Best-effort write to the shared site-side activity log."""
        client = self.require_client()
        client.write_activity(action, summary, details=details, actor_arn=self.actor_arn)

    def refresh_activity_log(self) -> None:
        def task():
            client = self.require_client()
            return client.scan_activity_log()

        def done(rows):
            self.activity_items = rows
            self.populate_activity_log()
            self.log(f"Loaded {len(rows)} shared activity log entries from {self.require_client().config.activity_log_table_name}.")

        self.run_background("Refresh shared activity log", task, done)

    def populate_activity_log(self) -> None:
        if not hasattr(self, "activity_tree"):
            return
        for row in self.activity_tree.get_children():
            self.activity_tree.delete(row)
        rows = self.activity_items or []
        for idx, item in enumerate(rows):
            actor = str(item.get("actor_arn", ""))
            actor_short = actor.split("/")[-1] if actor else ""
            self.activity_tree.insert(
                "",
                END,
                iid=str(idx),
                values=(
                    item.get("created_at", ""),
                    item.get("action", ""),
                    actor_short,
                    item.get("summary", ""),
                ),
            )
        self.selected_activity = None
        self.activity_detail.delete("1.0", END)

    def on_activity_select(self, _event=None) -> None:
        sel = self.activity_tree.selection()
        if not sel:
            return
        item = self.activity_items[int(sel[0])]
        self.selected_activity = item
        self.activity_detail.delete("1.0", END)
        self.activity_detail.insert("1.0", json.dumps(item, cls=JsonDecimalEncoder, indent=2, sort_keys=True))

    def export_activity_log(self) -> None:
        if not self.client:
            messagebox.showerror(APP_TITLE, "Connect to AWS first.")
            return
        default = Path.home() / "Downloads" / f"sports-activity-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path = filedialog.asksaveasfilename(
            title="Export shared activity log",
            initialfile=default.name,
            initialdir=str(default.parent),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        def task():
            client = self.require_client()
            rows = client.scan_activity_log(limit=10000)
            Path(path).write_text(json.dumps(rows, cls=JsonDecimalEncoder, indent=2, sort_keys=True), encoding="utf-8")
            client.write_activity(
                "activity_log_exported",
                "Shared activity log exported locally",
                actor_arn=self.actor_arn,
                details={"export_path": str(path), "entry_count": len(rows)},
            )
            return path, client.scan_activity_log()

        def done(result):
            saved_path, rows = result
            self.activity_items = rows
            self.populate_activity_log()
            self.log(f"Exported shared activity log to {saved_path}")

        self.run_background("Export shared activity log", task, done)

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
            client.write_activity(
                "suggestion_approved",
                f"Approved suggestion as official body: {payload.get('name', payload['id'])}",
                actor_arn=self.actor_arn,
                details={"suggestion_id": suggestion["id"], "collection": "sport_bodies", "item_id": payload["id"]},
            )
            self.refresh_after_approval("sport_bodies")
            self.refresh_activity_log()

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
            client.write_activity(
                "suggestion_approved",
                f"Approved suggestion as pathway: {payload.get('name', payload['id'])}",
                actor_arn=self.actor_arn,
                details={"suggestion_id": suggestion["id"], "collection": "pathways", "item_id": payload["id"]},
            )
            self.refresh_after_approval("pathways")
            self.refresh_activity_log()

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
            client = self.require_client()
            client.update_suggestion_status(suggestion["id"], "rejected")
            client.write_activity(
                "suggestion_rejected",
                f"Rejected suggestion: {suggestion.get('name', suggestion['id'])}",
                actor_arn=self.actor_arn,
                details={"suggestion_id": suggestion["id"]},
            )
            return client.scan_activity_log()

        def done(rows):
            self.activity_items = rows
            self.populate_activity_log()
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
            client = self.require_client()
            client.delete_item("suggestions", suggestion["id"])
            client.write_activity(
                "suggestion_deleted",
                f"Deleted suggestion: {suggestion.get('name', suggestion['id'])}",
                actor_arn=self.actor_arn,
                details={"suggestion_id": suggestion["id"]},
            )
            return client.scan_activity_log()

        def done(rows):
            self.activity_items = rows
            self.populate_activity_log()
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
            client = self.require_client()
            client.put_item(collection, payload)
            client.write_activity(
                "record_created",
                f"Created {collection} record: {payload.get('name', payload['id'])}",
                actor_arn=self.actor_arn,
                details={"collection": collection, "item_id": payload["id"]},
            )
            self.log(f"Saved new {collection} record: {payload['id']}")
            self.refresh_collection(collection)
            self.refresh_activity_log()

        JsonEditor(self.root, f"New {COLLECTIONS[collection]['label']} record", initial, save)

    def edit_selected_record(self) -> None:
        try:
            collection = self.record_collection_var.get()
            item = deepcopy(self.record_or_raise())
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        def save(payload: dict) -> None:
            client = self.require_client()
            client.put_item(collection, payload)
            client.write_activity(
                "record_updated",
                f"Updated {collection} record: {payload.get('name', payload['id'])}",
                actor_arn=self.actor_arn,
                details={"collection": collection, "item_id": payload["id"]},
            )
            self.log(f"Saved {collection} record: {payload['id']}")
            self.refresh_collection(collection)
            self.refresh_activity_log()

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
            client = self.require_client()
            client.delete_item(collection, item["id"])
            client.write_activity(
                "record_deleted",
                f"Deleted {collection} record: {item.get('name', item['id'])}",
                actor_arn=self.actor_arn,
                details={"collection": collection, "item_id": item["id"]},
            )
            return client.scan_activity_log()

        def done(rows):
            self.activity_items = rows
            self.populate_activity_log()
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
            client.write_activity(
                "catalogue_exported",
                "Catalogue tables exported locally",
                actor_arn=self.actor_arn,
                details={"export_path": str(path), "collections": {k: len(v) for k, v in data.items()}},
            )
            return path, client.scan_activity_log()

        def done(result):
            saved_path, rows = result
            self.activity_items = rows
            self.populate_activity_log()
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
            client.write_activity(
                "catalogue_imported",
                "Catalogue JSON imported/upserted",
                actor_arn=self.actor_arn,
                details={"import_path": str(path), "counts": counts},
            )
            refreshed = {collection: client.scan_all(collection) for collection in COLLECTIONS}
            activity_rows = client.scan_activity_log()
            return counts, refreshed, activity_rows

        def done(result):
            counts, refreshed, activity_rows = result
            self.items = refreshed
            self.activity_items = activity_rows
            self.populate_suggestions()
            self.populate_records()
            self.populate_activity_log()
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
