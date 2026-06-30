import json
import os
from decimal import Decimal
from typing import Any, Dict, Iterable, List

import boto3
from boto3.dynamodb.conditions import Attr

DDB = boto3.resource("dynamodb")
TOURNAMENTS_TABLE = DDB.Table(os.environ["TOURNAMENTS_TABLE"])
PLAYERS_TABLE = DDB.Table(os.environ["PLAYERS_TABLE"])
EVENTS_TABLE = DDB.Table(os.environ["EVENTS_TABLE"])
SPORT_BODIES_TABLE = DDB.Table(os.environ["SPORT_BODIES_TABLE"])

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Content-Type": "application/json",
}


def decimal_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError


def response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=decimal_default),
    }


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


def text_blob(item: Dict[str, Any]) -> str:
    return json.dumps(item, default=decimal_default).lower()


def handle_search(query: Dict[str, str]) -> Dict[str, Any]:
    q = (query.get("q") or "").strip().lower()
    if len(q) < 2:
        return response(200, {"organisations": [], "tournaments": [], "players": []})
    organisations = [item for item in scan_all(SPORT_BODIES_TABLE) if q in text_blob(item)]
    tournaments = [item for item in scan_all(TOURNAMENTS_TABLE) if q in text_blob(item)]
    players = [item for item in scan_all(PLAYERS_TABLE) if q in text_blob(item)]
    return response(200, {
        "organisations": sort_by_name(organisations),
        "tournaments": sort_by_date(tournaments),
        "players": sort_by_name(players),
    })


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return response(204, {})
    if method != "GET":
        return response(405, {"message": "Method not allowed"})

    raw_path = event.get("rawPath") or "/"
    path_parts = [part for part in raw_path.strip("/").split("/") if part]
    query = event.get("queryStringParameters") or {}

    try:
        if not path_parts or path_parts[0] == "health":
            return response(200, {"ok": True, "service": "sports-vk2ale-aggregator"})
        if path_parts[0] == "tournaments":
            return handle_tournaments(path_parts, query)
        if path_parts[0] == "players":
            return handle_players(path_parts, query)
        if path_parts[0] == "events":
            return handle_events(query)
        if path_parts[0] in {"organisations", "organizations", "sports-bodies"}:
            return handle_organisations(path_parts, query)
        if path_parts[0] == "search":
            return handle_search(query)
        return response(404, {"message": "Route not found"})
    except Exception as exc:  # noqa: BLE001 - return useful API error for starter project
        print(f"Unhandled error: {exc}")
        return response(500, {"message": "Internal server error"})
