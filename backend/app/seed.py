"""Idempotent, explicit demo loading: uv run python -m app.seed."""

import argparse
import json
from pathlib import Path

from app.core.database import SessionLocal
from app.services.ingestion import ingest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "sample-data/catalogue.json",
    )
    args = parser.parse_args()
    dataset = json.loads(args.file.read_text())
    if dataset["provider"] != "demo":
        raise ValueError("The demo loader accepts only provider=demo")
    with SessionLocal() as db:
        for artist in dataset["artists"]:
            ingest(db, lambda item=artist: item, "demo")
    print(f"Loaded {len(dataset['artists'])} fictional demo artists; safe to run again.")


if __name__ == "__main__":
    main()
