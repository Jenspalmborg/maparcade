"""Fetch every product's most similar products for MapGolf.

MapGolf moves along BehaviorGPT's own similarity, not the drawn map: each
turn offers "clubs" picked from the product's similar_products ranking.
Results are cached in data/neighbours.jsonl, so an interrupted run resumes.

Run:  uv run python scripts/neighbours.py
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from behaviorgpt import UnboxAIClient
from behaviorgpt._exceptions import UnboxAIError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "neighbours.jsonl"
DEPTH = 60
load_dotenv(ROOT / ".env")

catalog_id = json.loads((DATA / "productguessr.json").read_text())["catalog_id"]
client = UnboxAIClient(market="us", default_catalog_id=catalog_id)


def fetch(pid: str) -> dict | None:
    for _ in range(3):
        try:
            items = client.similar_products(pid, limit=DEPTH).products.items
            return {"id": pid, "n": [i.id for i in items if i.id != pid]}
        except (UnboxAIError, OSError):
            continue
    return None


def main() -> None:
    ids = [row[0] for row in json.loads((ROOT / "docs" / "data.json").read_text())["items"]]
    done = set()
    if CACHE.exists():
        done = {json.loads(line)["id"] for line in CACHE.open()}
    todo = [pid for pid in ids if pid not in done]
    print(f"{len(done)} cached, {len(todo)} to fetch")

    with CACHE.open("a") as out, ThreadPoolExecutor(max_workers=8) as pool:
        for k, row in enumerate(pool.map(fetch, todo), 1):
            if row:
                out.write(json.dumps(row) + "\n")
            if k % 500 == 0:
                out.flush()
                print(f"  {k}/{len(todo)}")
    print("done")


if __name__ == "__main__":
    main()
