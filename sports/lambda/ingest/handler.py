import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable

import boto3

DDB = boto3.resource("dynamodb")
TOURNAMENTS_TABLE = DDB.Table(os.environ["TOURNAMENTS_TABLE"])
PLAYERS_TABLE = DDB.Table(os.environ["PLAYERS_TABLE"])
EVENTS_TABLE = DDB.Table(os.environ["EVENTS_TABLE"])
SPORT_BODIES_TABLE = DDB.Table(os.environ["SPORT_BODIES_TABLE"])

DATA_FILE = Path(__file__).with_name("seed_public_sports.json")


def put_items(table, items: Iterable[Dict]) -> int:
    count = 0
    with table.batch_writer(overwrite_by_pkeys=["id"]) as batch:
        for item in items:
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            batch.put_item(Item=item)
            count += 1
    return count


def lambda_handler(event, context):
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    counts = {
        "tournaments": put_items(TOURNAMENTS_TABLE, payload.get("tournaments", [])),
        "players": put_items(PLAYERS_TABLE, payload.get("players", [])),
        "events": put_items(EVENTS_TABLE, payload.get("events", [])),
        "sport_bodies": put_items(SPORT_BODIES_TABLE, payload.get("sport_bodies", [])),
    }
    return {
        "statusCode": 200,
        "body": json.dumps({"ok": True, "seeded": counts}),
    }
