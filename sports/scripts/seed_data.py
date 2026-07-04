#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import boto3


def put_items(table, items: Iterable[dict]) -> int:
    count = 0
    with table.batch_writer(overwrite_by_pkeys=["id"]) as batch:
        for item in items:
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            batch.put_item(Item=item)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Sports.vk2ale DynamoDB tables")
    parser.add_argument("--tournaments-table", required=True)
    parser.add_argument("--players-table", required=True)
    parser.add_argument("--events-table", required=True)
    parser.add_argument("--sport-bodies-table", required=True)
    parser.add_argument("--top-players-table", required=True)
    parser.add_argument("--data-file", default="data/seed_public_sports.json")
    parser.add_argument("--region")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region) if args.region else boto3.Session()
    ddb = session.resource("dynamodb")
    payload = json.loads(Path(args.data_file).read_text(encoding="utf-8"))

    counts = {
        "tournaments": put_items(ddb.Table(args.tournaments_table), payload.get("tournaments", [])),
        "players": put_items(ddb.Table(args.players_table), payload.get("players", [])),
        "events": put_items(ddb.Table(args.events_table), payload.get("events", [])),
        "sport_bodies": put_items(ddb.Table(args.sport_bodies_table), payload.get("sport_bodies", [])),
        "top_players": put_items(ddb.Table(args.top_players_table), payload.get("top_players", [])),
    }
    print(json.dumps({"ok": True, "seeded": counts}, indent=2))


if __name__ == "__main__":
    main()
