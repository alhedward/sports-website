import json
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

DDB = boto3.resource("dynamodb")
TOURNAMENTS_TABLE = DDB.Table(os.environ["TOURNAMENTS_TABLE"])
PLAYERS_TABLE = DDB.Table(os.environ["PLAYERS_TABLE"])
EVENTS_TABLE = DDB.Table(os.environ["EVENTS_TABLE"])
SPORT_BODIES_TABLE = DDB.Table(os.environ["SPORT_BODIES_TABLE"])
TOP_PLAYERS_TABLE = DDB.Table(os.environ["TOP_PLAYERS_TABLE"])
SUGGESTIONS_TABLE = DDB.Table(os.environ["SUGGESTIONS_TABLE"])
ACTIVITY_LOG_TABLE = DDB.Table(os.environ["ACTIVITY_LOG_TABLE"])
PUBLIC_PUSH_SUBSCRIPTIONS_TABLE = DDB.Table(os.environ["PUBLIC_PUSH_SUBSCRIPTIONS_TABLE"])
ADMIN_DEVICES_TABLE = DDB.Table(os.environ["ADMIN_DEVICES_TABLE"])
ADMIN_PRELOGIN_ATTEMPTS_TABLE = DDB.Table(os.environ["ADMIN_PRELOGIN_ATTEMPTS_TABLE"])
COGNITO = boto3.client("cognito-idp")

ADMIN_ALLOWED_GROUPS = {
    group.strip()
    for group in os.environ.get("ADMIN_ALLOWED_GROUPS", "PrimaryAdmins,Admins,Editors").split(",")
    if group.strip()
}
PRIMARY_ADMIN_GROUP = os.environ.get("PRIMARY_ADMIN_GROUP", "PrimaryAdmins").strip() or "PrimaryAdmins"
DEVICE_APPROVAL_TTL_SECONDS = int(os.environ.get("DEVICE_APPROVAL_TTL_SECONDS", "1800"))

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Admin-Device-Id",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Content-Type": "application/json",
}

COLLECTION_TABLES = {
    "suggestions": SUGGESTIONS_TABLE,
    "sport_bodies": SPORT_BODIES_TABLE,
    "top_players": TOP_PLAYERS_TABLE,
    "pathways": PLAYERS_TABLE,
    "players": PLAYERS_TABLE,
    "tournaments": TOURNAMENTS_TABLE,
    "events": EVENTS_TABLE,
}

COLLECTION_SORTS = {
    "suggestions": ["status", "submitted_at", "name"],
    "sport_bodies": ["sport", "name"],
    "top_players": ["sport", "name"],
    "pathways": ["sport", "name"],
    "players": ["sport", "name"],
    "tournaments": ["start_date", "name"],
    "events": ["date", "name"],
}


def decimal_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError


def normalize_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(k): normalize_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_decimal(v) for v in value]
    return value


def response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=decimal_default),
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def epoch_seconds(dt: datetime | None = None) -> int:
    return int((dt or datetime.now(timezone.utc)).timestamp())

def request_ip(event: Dict[str, Any]) -> str:
    ctx = event.get("requestContext") or {}
    http = ctx.get("http") or {}
    headers = event.get("headers") or {}
    return http.get("sourceIp") or headers.get("x-forwarded-for", "").split(",")[0].strip() or "unknown"

def user_agent(event: Dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    return headers.get("user-agent") or headers.get("User-Agent") or "unknown"

def client_context(event: Dict[str, Any]) -> Dict[str, Any]:
    return {"ip": request_ip(event), "user_agent": user_agent(event)[:500]}

def put_activity_raw(action: str, summary: str, details: Dict[str, Any] | None = None) -> None:
    created_at = now_iso()
    item = {
        "id": f"log-{created_at.replace(':', '').replace('.', '-')}-{uuid.uuid4().hex[:10]}",
        "created_at": created_at,
        "action": action,
        "summary": summary,
        "actor_sub": "",
        "actor_username": "",
        "actor_email": "",
        "actor_groups": [],
        "source": "public_or_prelogin_api",
    }
    if details:
        item["details"] = details
    ACTIVITY_LOG_TABLE.put_item(Item=normalize_decimal(item))


def scan_all(table, *, filter_expression=None) -> List[Dict[str, Any]]:
    kwargs = {}
    if filter_expression is not None:
        kwargs["FilterExpression"] = filter_expression
    items: List[Dict[str, Any]] = []
    while True:
        result = table.scan(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def get_item(table, item_id: str) -> Dict[str, Any] | None:
    result = table.get_item(Key={"id": item_id})
    return result.get("Item")


def sort_by_date(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("start_date") or item.get("date") or "9999-99-99")


def sort_by_name(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("name", "").lower())


def sort_items(items: Iterable[Dict[str, Any]], fields: List[str]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: tuple(str(item.get(field, "")).lower() for field in fields))


def text_blob(item: Dict[str, Any]) -> str:
    return json.dumps(item, default=decimal_default).lower()


def parse_json_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ValueError("Request body must be valid JSON")
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


# ----------------------------- Public API -----------------------------

def handle_tournaments(path_parts: List[str], query: Dict[str, str]) -> Dict[str, Any]:
    if len(path_parts) == 1:
        sport = query.get("sport")
        items = scan_all(TOURNAMENTS_TABLE, filter_expression=Attr("sport").contains(sport)) if sport else scan_all(TOURNAMENTS_TABLE)
        return response(200, sort_by_date(items))
    item = get_item(TOURNAMENTS_TABLE, path_parts[1])
    if not item:
        return response(404, {"message": "Tournament not found"})
    return response(200, item)


def handle_players(path_parts: List[str], query: Dict[str, str]) -> Dict[str, Any]:
    if len(path_parts) == 1:
        tournament_id = query.get("tournament_id")
        sport = query.get("sport")
        if tournament_id:
            items = scan_all(PLAYERS_TABLE, filter_expression=Attr("tournament_ids").contains(tournament_id))
        elif sport:
            items = scan_all(PLAYERS_TABLE, filter_expression=Attr("sport").contains(sport))
        else:
            items = scan_all(PLAYERS_TABLE)
        return response(200, sort_by_name(items))
    item = get_item(PLAYERS_TABLE, path_parts[1])
    if not item:
        return response(404, {"message": "Pathway profile not found"})
    return response(200, item)


def handle_top_players(path_parts: List[str], query: Dict[str, str]) -> Dict[str, Any]:
    if len(path_parts) == 1:
        sport = query.get("sport")
        genre = query.get("genre")
        body_id = query.get("body_id")
        items = scan_all(TOP_PLAYERS_TABLE)
        if sport:
            needle = sport.lower()
            items = [item for item in items if needle in str(item.get("sport", "")).lower() or needle in text_blob(item)]
        if genre:
            needle = genre.lower()
            items = [item for item in items if needle in str(item.get("genre", "")).lower()]
        if body_id:
            items = [item for item in items if body_id in item.get("related_body_ids", [])]
        return response(200, sort_by_name(items))
    item = get_item(TOP_PLAYERS_TABLE, path_parts[1])
    if not item:
        return response(404, {"message": "Top player spotlight not found"})
    return response(200, item)



def handle_public_notifications(event: Dict[str, Any], method: str, path_parts: List[str]) -> Dict[str, Any]:
    if method != "POST":
        return response(405, {"message": "Method not allowed"})
    payload = parse_json_body(event)
    action = path_parts[1] if len(path_parts) > 1 else "subscribe"
    subscription = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else {}
    endpoint = str(subscription.get("endpoint") or payload.get("endpoint") or "").strip()
    if not endpoint:
        return response(400, {"message": "Push subscription endpoint is required"})
    import hashlib
    endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
    sub_id = f"public-push-{endpoint_hash[:32]}"
    now = now_iso()
    if action in {"unsubscribe", "disable"}:
        existing = get_item(PUBLIC_PUSH_SUBSCRIPTIONS_TABLE, sub_id) or {"id": sub_id}
        existing.update({"status": "disabled", "disabled_at": now, "updated_at": now})
        PUBLIC_PUSH_SUBSCRIPTIONS_TABLE.put_item(Item=normalize_decimal(existing))
        return response(200, {"ok": True, "id": sub_id, "status": "disabled"})
    item = {
        "id": sub_id,
        "type": "public_notifications",
        "status": "active",
        "endpoint_hash": endpoint_hash,
        "subscription": subscription or {"endpoint": endpoint},
        "topics": payload.get("topics") if isinstance(payload.get("topics"), list) else ["sports-updates"],
        "created_at": now,
        "updated_at": now,
        "client": client_context(event),
    }
    PUBLIC_PUSH_SUBSCRIPTIONS_TABLE.put_item(Item=normalize_decimal(item))
    return response(201, {"ok": True, "id": sub_id, "status": "active"})


def cognito_admin_user_for_email(email: str) -> Dict[str, Any] | None:
    pool_id = os.environ.get("ADMIN_USER_POOL_ID", "")
    if not pool_id:
        return None
    try:
        result = COGNITO.list_users(
            UserPoolId=pool_id,
            Filter=f'email = "{email}"',
            Limit=1,
        )
    except ClientError as exc:
        print(f"Cognito list_users failed: {exc}")
        return None
    users = result.get("Users", [])
    if not users:
        return None
    user = users[0]
    username = user.get("Username") or email
    try:
        groups = COGNITO.admin_list_groups_for_user(UserPoolId=pool_id, Username=username).get("Groups", [])
    except ClientError as exc:
        print(f"Cognito admin_list_groups_for_user failed: {exc}")
        groups = []
    group_names = [group.get("GroupName", "") for group in groups]
    if not ADMIN_ALLOWED_GROUPS.intersection(group_names):
        return None
    attrs = {attr.get("Name"): attr.get("Value") for attr in user.get("Attributes", [])}
    return {"username": username, "sub": attrs.get("sub", ""), "email": attrs.get("email", email), "groups": group_names}


def handle_admin_precheck(event: Dict[str, Any], method: str) -> Dict[str, Any]:
    if method != "POST":
        return response(405, {"message": "Method not allowed"})
    payload = parse_json_body(event)
    email = str(payload.get("email", "")).strip().lower()
    device_id = str(payload.get("device_id", "")).strip()[:160]
    device_label = str(payload.get("device_label", "Admin device")).strip()[:160] or "Admin device"
    ctx = client_context(event)
    import hashlib, time
    key_material = f"{email}|{ctx.get('ip')}"
    attempt_id = "admin-precheck-" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:40]
    now_epoch = epoch_seconds()
    attempt = get_item(ADMIN_PRELOGIN_ATTEMPTS_TABLE, attempt_id) or {"id": attempt_id, "failed_count": 0}
    locked_until = int(attempt.get("locked_until", 0) or 0)
    # Fixed server-side minimum response delay to slow guessing and keep timing bland.
    time.sleep(5)
    if locked_until and locked_until > now_epoch:
        put_activity_raw("admin_precheck_rate_limited", "Admin pre-login check rate-limited", {"email_hash": hashlib.sha256(email.encode()).hexdigest(), **ctx})
        return response(403, {"ok": False, "message": "Access denied"})

    user = cognito_admin_user_for_email(email) if email else None
    if user and device_id:
        user_devices = scan_all(ADMIN_DEVICES_TABLE, filter_expression=Attr("email").eq(email))
        matching = next((item for item in user_devices if item.get("device_id") == device_id), None)
        status = str((matching or {}).get("status", ""))

        if status == "active":
            ADMIN_PRELOGIN_ATTEMPTS_TABLE.delete_item(Key={"id": attempt_id})
            put_activity_raw("admin_precheck_allowed", "Admin pre-login check allowed", {"email_hash": hashlib.sha256(email.encode()).hexdigest(), "device_id": device_id, **ctx})
            return response(200, {"ok": True, "message": "Continue to Cognito login"})

        if status == "approved":
            approval_expires = int((matching or {}).get("approval_expires", 0) or 0)
            if approval_expires > now_epoch:
                ADMIN_PRELOGIN_ATTEMPTS_TABLE.delete_item(Key={"id": attempt_id})
                put_activity_raw("admin_precheck_allowed_approved_device", "Approved admin device allowed to continue to Cognito", {"email_hash": hashlib.sha256(email.encode()).hexdigest(), "device_id": device_id, **ctx})
                return response(200, {"ok": True, "message": "Continue to Cognito login"})

        # Preserve the original bootstrap behaviour only when this Cognito user has
        # never had any device record. Once a device exists, additional hardware
        # must be approved by a PrimaryAdmin.
        if not user_devices:
            ADMIN_PRELOGIN_ATTEMPTS_TABLE.delete_item(Key={"id": attempt_id})
            put_activity_raw("admin_precheck_allowed_first_device", "First admin device allowed to continue to Cognito", {"email_hash": hashlib.sha256(email.encode()).hexdigest(), "device_id": device_id, **ctx})
            return response(200, {"ok": True, "message": "Continue to Cognito login"})

        now = now_iso()
        item_id = f"admin-device-{user.get('sub')}-{device_id}"[:240]
        request_count = int((matching or {}).get("request_count", 0) or 0) + 1
        pending = {
            **(matching or {}),
            "id": item_id,
            "device_id": device_id,
            "user_sub": user.get("sub", ""),
            "email": user.get("email", email),
            "username": user.get("username", ""),
            "groups": user.get("groups", []),
            "device_label": device_label,
            "status": "pending",
            "requested_at": (matching or {}).get("requested_at", now),
            "last_requested_at": now,
            "request_count": request_count,
            "updated_at": now,
            "client": ctx,
        }
        for field in ("approved_at", "approved_by_sub", "approved_by_email", "approval_expires", "rejected_at", "rejected_by_sub", "rejected_by_email", "revoked_at"):
            pending.pop(field, None)
        ADMIN_DEVICES_TABLE.put_item(Item=normalize_decimal(pending))
        ADMIN_PRELOGIN_ATTEMPTS_TABLE.delete_item(Key={"id": attempt_id})
        put_activity_raw(
            "admin_device_approval_requested",
            f"Admin device approval requested: {device_label}",
            {"email_hash": hashlib.sha256(email.encode()).hexdigest(), "device_id": device_id, "device_label": device_label, **ctx},
        )
        return response(403, {
            "ok": False,
            "code": "DEVICE_APPROVAL_PENDING",
            "message": "This device is awaiting approval from a PrimaryAdmin.",
        })

    failed = int(attempt.get("failed_count", 0) or 0) + 1
    update = {"id": attempt_id, "failed_count": failed, "updated_at": now_iso(), "ttl": now_epoch + 86400, **ctx}
    if failed >= 5:
        update["locked_until"] = now_epoch + 900
        put_activity_raw("admin_lockout_started", "Admin pre-login temporary lockout started", {"email_hash": hashlib.sha256(email.encode()).hexdigest(), **ctx})
    ADMIN_PRELOGIN_ATTEMPTS_TABLE.put_item(Item=normalize_decimal(update))
    put_activity_raw("admin_precheck_denied", "Admin pre-login check denied", {"email_hash": hashlib.sha256(email.encode()).hexdigest(), **ctx})
    return response(403, {"ok": False, "message": "Access denied"})

def handle_suggestions(event: Dict[str, Any], method: str) -> Dict[str, Any]:
    if method == "GET":
        return response(200, {"message": "Suggestions are accepted by POST and held for moderation before publication."})
    if method != "POST":
        return response(405, {"message": "Method not allowed"})

    payload = parse_json_body(event)
    name = str(payload.get("name", "")).strip()
    official_url = str(payload.get("official_url", "")).strip()
    sport = str(payload.get("sport", "")).strip()
    if not name or not official_url or not sport:
        return response(400, {"message": "name, official_url and sport are required"})
    if not official_url.startswith(("https://", "http://")):
        return response(400, {"message": "official_url must start with http:// or https://"})

    submitted_at = now_iso()
    suggestion_id = f"suggestion-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    item = {
        "id": suggestion_id,
        "status": "pending_review",
        "name": name[:160],
        "official_url": official_url[:500],
        "sport": sport[:100],
        "region": str(payload.get("region", "")).strip()[:100],
        "suggestion_type": str(payload.get("suggestion_type", "sport_body")).strip()[:60],
        "submitter_note": str(payload.get("submitter_note", "")).strip()[:1000],
        "submitted_at": submitted_at,
        "updated_at": submitted_at,
        "source": "public_site_suggestion",
    }
    SUGGESTIONS_TABLE.put_item(Item=item)
    put_activity_raw("public_suggestion_submitted", f"New public suggestion submitted: {name}", {"suggestion_id": suggestion_id, "sport": sport, "notification_status": "queued_for_admin_pwa_push_scaffold", **client_context(event)})
    return response(202, {"ok": True, "id": suggestion_id, "status": "pending_review"})


def handle_events(query: Dict[str, str]) -> Dict[str, Any]:
    tournament_id = query.get("tournament_id")
    items = scan_all(EVENTS_TABLE, filter_expression=Attr("tournament_id").eq(tournament_id)) if tournament_id else scan_all(EVENTS_TABLE)
    return response(200, sort_by_date(items))


def handle_organisations(path_parts: List[str], query: Dict[str, str]) -> Dict[str, Any]:
    if len(path_parts) == 1:
        sport = query.get("sport")
        region = query.get("region")
        items = scan_all(SPORT_BODIES_TABLE)
        if sport:
            needle = sport.lower()
            items = [item for item in items if needle in text_blob(item)]
        if region:
            needle = region.lower()
            items = [item for item in items if needle in str(item.get("region", "")).lower()]
        return response(200, sort_by_name(items))
    item = get_item(SPORT_BODIES_TABLE, path_parts[1])
    if not item:
        return response(404, {"message": "Organisation not found"})
    return response(200, item)


def handle_search(query: Dict[str, str]) -> Dict[str, Any]:
    q = (query.get("q") or "").strip().lower()
    if len(q) < 2:
        return response(200, {"organisations": [], "tournaments": [], "players": [], "top_players": []})
    organisations = [item for item in scan_all(SPORT_BODIES_TABLE) if q in text_blob(item)]
    tournaments = [item for item in scan_all(TOURNAMENTS_TABLE) if q in text_blob(item)]
    players = [item for item in scan_all(PLAYERS_TABLE) if q in text_blob(item)]
    top_players = [item for item in scan_all(TOP_PLAYERS_TABLE) if q in text_blob(item)]
    return response(200, {
        "organisations": sort_by_name(organisations),
        "tournaments": sort_by_date(tournaments),
        "players": sort_by_name(players),
        "top_players": sort_by_name(top_players),
    })


# ----------------------------- Admin API -----------------------------

def parse_groups(raw_groups: Any) -> List[str]:
    """Parse Cognito group claims from API Gateway's JWT event.

    API Gateway normally forwards Cognito groups as a list-like claim, but across
    token types/provider serialisation it can arrive as a Python list, a JSON
    list string, a comma-separated string, or the slightly annoying
    "[PrimaryAdmins]" string. Keep this deliberately forgiving so a valid
    admin does not get blocked because of claim formatting.
    """
    if not raw_groups:
        return []
    if isinstance(raw_groups, (list, tuple, set)):
        return [str(group).strip().strip("'\"") for group in raw_groups if str(group).strip()]
    value = str(raw_groups).strip()
    if value.startswith("[") and value.endswith("]"):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(group).strip().strip("'\"") for group in decoded if str(group).strip()]
        except json.JSONDecodeError:
            value = value[1:-1].strip()
    return [part.strip().strip("'\"") for part in value.split(",") if part.strip().strip("'\"")]


def groups_from_claims(claims: Dict[str, Any]) -> List[str]:
    seen: List[str] = []
    for key in ("cognito:groups", "groups", "cognito_groups"):
        for group in parse_groups(claims.get(key)):
            if group and group not in seen:
                seen.append(group)
    return seen


def admin_claims_or_raise(event: Dict[str, Any]) -> Dict[str, Any]:
    claims = (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
    groups = groups_from_claims(claims)
    if ADMIN_ALLOWED_GROUPS and not ADMIN_ALLOWED_GROUPS.intersection(groups):
        print(
            "Admin authorisation denied",
            json.dumps({
                "expected_groups": sorted(ADMIN_ALLOWED_GROUPS),
                "parsed_groups": groups,
                "claim_keys": sorted(claims.keys()),
                "raw_group_claim": claims.get("cognito:groups"),
                "token_use": claims.get("token_use"),
                "client": claims.get("aud") or claims.get("client_id"),
                "username": claims.get("username") or claims.get("cognito:username"),
                "email": claims.get("email"),
            }, default=str),
        )
        raise PermissionError(f"Authenticated user is not in an allowed admin group; parsed_groups={groups}; expected={sorted(ADMIN_ALLOWED_GROUPS)}")
    claims = dict(claims)
    claims["_groups"] = groups
    return claims


def actor_from_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sub": claims.get("sub", ""),
        "username": claims.get("username") or claims.get("cognito:username") or "",
        "email": claims.get("email", ""),
        "groups": claims.get("_groups", []),
    }


def require_primary_admin(claims: Dict[str, Any]) -> None:
    groups = set(claims.get("_groups", []))
    if PRIMARY_ADMIN_GROUP not in groups:
        raise PermissionError(f"This action requires membership in {PRIMARY_ADMIN_GROUP}")


def request_header(event: Dict[str, Any], name: str) -> str:
    wanted = name.lower()
    for key, value in (event.get("headers") or {}).items():
        if str(key).lower() == wanted:
            return str(value or "").strip()
    return ""


def admin_device_item_id(user_sub: str, device_id: str) -> str:
    return f"admin-device-{user_sub}-{device_id}"[:240]


def require_active_admin_device(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    actor = actor_from_claims(claims)
    device_id = request_header(event, "x-admin-device-id")[:160]
    if not actor.get("sub") or not device_id:
        raise PermissionError("A registered admin device is required")
    item = get_item(ADMIN_DEVICES_TABLE, admin_device_item_id(actor.get("sub", ""), device_id))
    if not item or item.get("status") != "active":
        raise PermissionError("This admin device is not active")
    return item


def write_activity(action: str, summary: str, *, claims: Dict[str, Any] | None = None, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    created_at = now_iso()
    actor = actor_from_claims(claims or {})
    item = {
        "id": f"log-{created_at.replace(':', '').replace('.', '-')}-{uuid.uuid4().hex[:10]}",
        "created_at": created_at,
        "action": action,
        "summary": summary,
        "actor_sub": actor.get("sub", ""),
        "actor_username": actor.get("username", ""),
        "actor_email": actor.get("email", ""),
        "actor_groups": actor.get("groups", []),
        "source": "admin_api",
    }
    if details:
        item["details"] = details
    ACTIVITY_LOG_TABLE.put_item(Item=normalize_decimal(item))
    return item


def collection_table(collection: str):
    if collection not in COLLECTION_TABLES:
        raise ValueError(f"Unknown collection: {collection}")
    return COLLECTION_TABLES[collection]


def admin_collection_get(collection: str, item_id: str | None = None) -> Dict[str, Any]:
    table = collection_table(collection)
    if item_id:
        item = get_item(table, item_id)
        if not item:
            return response(404, {"message": "Record not found"})
        return response(200, item)
    return response(200, sort_items(scan_all(table), COLLECTION_SORTS.get(collection, ["name"])))


def admin_collection_put(collection: str, item_id: str, event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    table = collection_table(collection)
    payload = parse_json_body(event)
    if not payload.get("id"):
        payload["id"] = item_id
    if payload["id"] != item_id:
        return response(400, {"message": "Payload id must match URL id"})
    existing = get_item(table, item_id)
    payload.setdefault("created_at", existing.get("created_at") if existing else now_iso())
    payload["updated_at"] = now_iso()
    table.put_item(Item=normalize_decimal(payload))
    write_activity(
        "record_upserted",
        f"Upserted {collection} record: {payload.get('name', item_id)}",
        claims=claims,
        details={"collection": collection, "item_id": item_id, "had_existing_record": bool(existing)},
    )
    return response(200, payload)


def admin_collection_delete(collection: str, item_id: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    table = collection_table(collection)
    existing = get_item(table, item_id)
    table.delete_item(Key={"id": item_id})
    write_activity(
        "record_deleted",
        f"Deleted {collection} record: {existing.get('name', item_id) if existing else item_id}",
        claims=claims,
        details={"collection": collection, "item_id": item_id},
    )
    return response(200, {"ok": True, "id": item_id})


def build_sport_body_from_suggestion(suggestion: Dict[str, Any]) -> Dict[str, Any]:
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


def build_pathway_from_suggestion(suggestion: Dict[str, Any]) -> Dict[str, Any]:
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


def slugify(value: str, prefix: str = "") -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = f"item-{int(datetime.now(timezone.utc).timestamp())}"
    return f"{prefix}{slug}" if prefix else slug


def admin_update_suggestion_status(suggestion_id: str, status: str, extra: Dict[str, Any] | None, claims: Dict[str, Any]) -> Dict[str, Any]:
    suggestion = get_item(SUGGESTIONS_TABLE, suggestion_id)
    if not suggestion:
        return response(404, {"message": "Suggestion not found"})
    suggestion["status"] = status
    suggestion["reviewed_at"] = now_iso()
    suggestion["updated_at"] = now_iso()
    if extra:
        suggestion.update(extra)
    SUGGESTIONS_TABLE.put_item(Item=normalize_decimal(suggestion))
    write_activity(
        f"suggestion_{status}",
        f"Suggestion {status}: {suggestion.get('name', suggestion_id)}",
        claims=claims,
        details={"suggestion_id": suggestion_id, "extra": extra or {}},
    )
    return response(200, suggestion)


def handle_admin_suggestion(path_parts: List[str], event: Dict[str, Any], method: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    # handle_admin() passes only the path parts after /admin/suggestions.
    # For /admin/suggestions/{id}/status this function receives [{id}, "status"].
    # Older builds accidentally treated path_parts[1] as the id, which broke
    # Cognito/API-mode approve/reject/status operations while boto3_direct still worked.
    if len(path_parts) < 1:
        return response(400, {"message": "Suggestion id is required"})
    suggestion_id = path_parts[0]
    action = path_parts[1] if len(path_parts) > 1 else ""

    if action == "status" and method == "POST":
        payload = parse_json_body(event)
        status = str(payload.get("status", "")).strip()
        if status not in {"pending_review", "approved", "rejected", "archived"}:
            return response(400, {"message": "Invalid status"})
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        return admin_update_suggestion_status(suggestion_id, status, extra, claims)

    suggestion = get_item(SUGGESTIONS_TABLE, suggestion_id)
    if not suggestion:
        return response(404, {"message": "Suggestion not found"})

    if action in {"approve-body", "approve-as-body"} and method == "POST":
        payload = parse_json_body(event)
        record = payload.get("record") if isinstance(payload.get("record"), dict) else build_sport_body_from_suggestion(suggestion)
        SPORT_BODIES_TABLE.put_item(Item=normalize_decimal(record))
        return admin_update_suggestion_status(
            suggestion_id,
            "approved",
            {"approved_collection": "sport_bodies", "approved_item_id": record["id"]},
            claims,
        )

    if action in {"approve-pathway", "approve-as-pathway"} and method == "POST":
        payload = parse_json_body(event)
        record = payload.get("record") if isinstance(payload.get("record"), dict) else build_pathway_from_suggestion(suggestion)
        PLAYERS_TABLE.put_item(Item=normalize_decimal(record))
        return admin_update_suggestion_status(
            suggestion_id,
            "approved",
            {"approved_collection": "pathways", "approved_item_id": record["id"]},
            claims,
        )

    if action == "reject" and method == "POST":
        return admin_update_suggestion_status(suggestion_id, "rejected", {}, claims)

    return response(404, {"message": "Admin suggestion route not found"})


def handle_activity_log(path_parts: List[str], event: Dict[str, Any], method: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    if method == "GET":
        limit = 500
        query = event.get("queryStringParameters") or {}
        try:
            limit = min(max(int(query.get("limit", "500")), 1), 10000)
        except ValueError:
            limit = 500
        items = scan_all(ACTIVITY_LOG_TABLE)
        items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return response(200, items[:limit])
    if method == "POST":
        payload = parse_json_body(event)
        action = str(payload.get("action", "admin_activity")).strip()[:120]
        summary = str(payload.get("summary", "Admin activity")).strip()[:500]
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        item = write_activity(action, summary, claims=claims, details=details)
        return response(201, item)
    return response(405, {"message": "Method not allowed"})



def handle_admin_devices(path_parts: List[str], event: Dict[str, Any], method: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    actor = actor_from_claims(claims)
    email = str(actor.get("email") or "").lower()
    if method == "GET":
        require_active_admin_device(event, claims)
        items = scan_all(ADMIN_DEVICES_TABLE, filter_expression=Attr("email").eq(email)) if email else []
        items.sort(key=lambda item: str(item.get("last_seen_at", item.get("registered_at", item.get("requested_at", "")))), reverse=True)
        return response(200, items)

    payload = parse_json_body(event)
    if method == "POST":
        device_id = str(payload.get("device_id", "")).strip()[:160]
        if not device_id:
            return response(400, {"message": "device_id is required"})
        header_device_id = request_header(event, "x-admin-device-id")[:160]
        if header_device_id != device_id:
            return response(400, {"message": "Device header and payload do not match"})

        now = now_iso()
        item_id = admin_device_item_id(actor.get("sub", ""), device_id)
        existing = get_item(ADMIN_DEVICES_TABLE, item_id) or {}
        actor_devices = scan_all(ADMIN_DEVICES_TABLE, filter_expression=Attr("email").eq(email)) if email else []
        existing_status = str(existing.get("status", ""))
        is_first_device = not actor_devices

        if not is_first_device and existing_status not in {"active", "approved"}:
            return response(403, {"message": "This device must be approved by a PrimaryAdmin before registration"})
        if existing_status == "approved":
            approval_expires = int(existing.get("approval_expires", 0) or 0)
            if approval_expires <= epoch_seconds():
                existing["status"] = "pending"
                existing["updated_at"] = now
                ADMIN_DEVICES_TABLE.put_item(Item=normalize_decimal(existing))
                return response(403, {"message": "Device approval expired; request approval again"})

        item = {
            **existing,
            "id": item_id,
            "device_id": device_id,
            "user_sub": actor.get("sub", ""),
            "email": email,
            "username": actor.get("username", ""),
            "groups": actor.get("groups", []),
            "device_label": str(payload.get("device_label", existing.get("device_label", "Admin device"))).strip()[:160] or "Admin device",
            "status": "active",
            "notifications_enabled": bool(payload.get("notifications_enabled", existing.get("notifications_enabled", False))),
            "push_subscription": payload.get("push_subscription") if isinstance(payload.get("push_subscription"), dict) else existing.get("push_subscription"),
            "registered_at": existing.get("registered_at", now),
            "activated_at": existing.get("activated_at", now),
            "last_seen_at": now,
            "updated_at": now,
            "client": client_context(event),
        }
        for field in ("approval_expires", "rejected_at", "rejected_by_sub", "rejected_by_email", "revoked_at"):
            item.pop(field, None)
        ADMIN_DEVICES_TABLE.put_item(Item=normalize_decimal(item))
        action = "admin_device_activated" if existing_status == "approved" else "admin_device_registered"
        write_activity(action, f"Admin device registered/updated: {item.get('device_label')}", claims=claims, details={"device_id": device_id})
        return response(201, item)

    if method == "DELETE" and path_parts:
        require_active_admin_device(event, claims)
        device_id = path_parts[0]
        item_id = admin_device_item_id(actor.get("sub", ""), device_id)
        existing = get_item(ADMIN_DEVICES_TABLE, item_id)
        if not existing:
            return response(404, {"message": "Device not found"})
        existing["status"] = "revoked"
        existing["revoked_at"] = now_iso()
        existing["updated_at"] = now_iso()
        ADMIN_DEVICES_TABLE.put_item(Item=normalize_decimal(existing))
        write_activity("admin_device_revoked", f"Admin device revoked: {existing.get('device_label', device_id)}", claims=claims, details={"device_id": device_id})
        return response(200, {"ok": True, "device_id": device_id, "status": "revoked"})
    return response(405, {"message": "Method not allowed"})


def handle_admin_device_requests(path_parts: List[str], event: Dict[str, Any], method: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    require_active_admin_device(event, claims)
    require_primary_admin(claims)
    actor = actor_from_claims(claims)

    if method == "GET" and not path_parts:
        items = [item for item in scan_all(ADMIN_DEVICES_TABLE) if item.get("status") == "pending"]
        items.sort(key=lambda item: str(item.get("last_requested_at", item.get("requested_at", ""))), reverse=True)
        return response(200, items)

    if method == "POST" and len(path_parts) == 2 and path_parts[1] in {"approve", "reject"}:
        item_id = path_parts[0]
        item = get_item(ADMIN_DEVICES_TABLE, item_id)
        if not item:
            return response(404, {"message": "Device request not found"})
        if item.get("status") != "pending":
            return response(409, {"message": "Device request is no longer pending"})
        now = now_iso()
        action = path_parts[1]
        if action == "approve":
            item["status"] = "approved"
            item["approved_at"] = now
            item["approved_by_sub"] = actor.get("sub", "")
            item["approved_by_email"] = actor.get("email", "")
            item["approval_expires"] = epoch_seconds() + DEVICE_APPROVAL_TTL_SECONDS
            item["updated_at"] = now
            summary = f"Admin device approved: {item.get('device_label', item.get('device_id', 'device'))}"
            activity_action = "admin_device_approved"
        else:
            item["status"] = "revoked"
            item["rejected_at"] = now
            item["rejected_by_sub"] = actor.get("sub", "")
            item["rejected_by_email"] = actor.get("email", "")
            item["updated_at"] = now
            item.pop("approval_expires", None)
            summary = f"Admin device request rejected: {item.get('device_label', item.get('device_id', 'device'))}"
            activity_action = "admin_device_rejected"
        ADMIN_DEVICES_TABLE.put_item(Item=normalize_decimal(item))
        write_activity(activity_action, summary, claims=claims, details={"device_id": item.get("device_id", ""), "request_user": item.get("email", "")})
        return response(200, item)

    return response(404, {"message": "Admin device request route not found"})

def handle_admin(event: Dict[str, Any], method: str, path_parts: List[str], query: Dict[str, str]) -> Dict[str, Any]:
    claims = admin_claims_or_raise(event)
    if not path_parts or path_parts[0] == "me":
        return response(200, {"authenticated": True, "actor": actor_from_claims(claims)})

    if path_parts[0] == "devices":
        return handle_admin_devices(path_parts[1:], event, method, claims)

    if path_parts[0] == "device-requests":
        return handle_admin_device_requests(path_parts[1:], event, method, claims)

    # Every other protected admin operation requires an active device as well as
    # a valid Cognito token. This makes the pre-login device approval meaningful
    # even if someone attempts to bypass the PWA and call Cognito directly.
    require_active_admin_device(event, claims)

    if path_parts[0] == "activity-log":
        return handle_activity_log(path_parts[1:], event, method, claims)

    if path_parts[0] == "collections":
        if len(path_parts) < 2:
            return response(400, {"message": "Collection name is required"})
        collection = path_parts[1]
        item_id = path_parts[2] if len(path_parts) > 2 else None
        if method == "GET":
            return admin_collection_get(collection, item_id)
        if not item_id:
            return response(400, {"message": "Record id is required for write/delete operations"})
        if method in {"PUT", "POST"}:
            return admin_collection_put(collection, item_id, event, claims)
        if method == "DELETE":
            return admin_collection_delete(collection, item_id, claims)
        return response(405, {"message": "Method not allowed"})

    if path_parts[0] == "suggestions":
        return handle_admin_suggestion(path_parts[1:], event, method, claims)

    return response(404, {"message": "Admin route not found"})


# ----------------------------- Entry point -----------------------------

def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return response(204, {})
    raw_path = event.get("rawPath") or "/"
    path_parts = [part for part in raw_path.strip("/").split("/") if part]
    query = event.get("queryStringParameters") or {}

    try:
        if path_parts and path_parts[0] == "admin":
            return handle_admin(event, method, path_parts[1:], query)
        if path_parts and path_parts[0] == "admin-precheck":
            return handle_admin_precheck(event, method)
        if path_parts and path_parts[0] == "notifications":
            return handle_public_notifications(event, method, path_parts)

        if path_parts and path_parts[0] != "suggestions" and method != "GET":
            return response(405, {"message": "Method not allowed"})
        if not path_parts or path_parts[0] == "health":
            return response(200, {"ok": True, "service": "sports-vk2ale-aggregator"})
        if path_parts[0] == "tournaments":
            return handle_tournaments(path_parts, query)
        if path_parts[0] == "players":
            if method != "GET":
                return response(405, {"message": "Method not allowed"})
            return handle_players(path_parts, query)
        if path_parts[0] in {"top-players", "top_players", "athletes"}:
            if method != "GET":
                return response(405, {"message": "Method not allowed"})
            return handle_top_players(path_parts, query)
        if path_parts[0] == "suggestions":
            return handle_suggestions(event, method)
        if path_parts[0] == "events":
            return handle_events(query)
        if path_parts[0] in {"organisations", "organizations", "sports-bodies"}:
            return handle_organisations(path_parts, query)
        if path_parts[0] == "search":
            return handle_search(query)
        return response(404, {"message": "Route not found"})
    except PermissionError as exc:
        return response(403, {"message": str(exc)})
    except ValueError as exc:
        return response(400, {"message": str(exc)})
    except Exception as exc:  # noqa: BLE001 - return useful API error for starter project
        print(f"Unhandled error: {exc}")
        return response(500, {"message": "Internal server error"})
