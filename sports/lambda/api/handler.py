import json
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

import boto3
from boto3.dynamodb.conditions import Attr

DDB = boto3.resource("dynamodb")
TOURNAMENTS_TABLE = DDB.Table(os.environ["TOURNAMENTS_TABLE"])
PLAYERS_TABLE = DDB.Table(os.environ["PLAYERS_TABLE"])
EVENTS_TABLE = DDB.Table(os.environ["EVENTS_TABLE"])
SPORT_BODIES_TABLE = DDB.Table(os.environ["SPORT_BODIES_TABLE"])
TOP_PLAYERS_TABLE = DDB.Table(os.environ["TOP_PLAYERS_TABLE"])
SUGGESTIONS_TABLE = DDB.Table(os.environ["SUGGESTIONS_TABLE"])
ACTIVITY_LOG_TABLE = DDB.Table(os.environ["ACTIVITY_LOG_TABLE"])

ADMIN_ALLOWED_GROUPS = {
    group.strip()
    for group in os.environ.get("ADMIN_ALLOWED_GROUPS", "PrimaryAdmins,Admins,Editors").split(",")
    if group.strip()
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
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
    if len(path_parts) < 2:
        return response(400, {"message": "Suggestion id is required"})
    suggestion_id = path_parts[1]
    action = path_parts[2] if len(path_parts) > 2 else ""

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


def handle_admin(event: Dict[str, Any], method: str, path_parts: List[str], query: Dict[str, str]) -> Dict[str, Any]:
    claims = admin_claims_or_raise(event)
    if not path_parts or path_parts[0] == "me":
        return response(200, {"authenticated": True, "actor": actor_from_claims(claims)})

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
