"""Turn the harvested products into a catalog parquet and embed it.

The API hands product fields back as strings ("None", "[1, 2, 3]"), so each
column is converted back to the type docs/catalog-format.md asks for.

Run:  uv run python scripts/embed.py            # all products
      uv run python scripts/embed.py --sample 300  # quick test upload first
"""

import ast
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from behaviorgpt import UnboxAIClient
from behaviorgpt.resources.catalogs import CATALOG_SCHEMA
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")


def text(v) -> str | None:
    return None if v in (None, "", "None", "nan") else str(v)


def integer(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def listed(v, cast):
    if isinstance(v, list):
        return [cast(x) for x in v]
    if text(v) is None:
        return None
    try:
        parsed = ast.literal_eval(v)
    except (ValueError, SyntaxError):
        return None
    return [cast(x) for x in parsed] if isinstance(parsed, (list, tuple)) else None


def to_row(p: dict) -> dict:
    sales = listed(p.get("sales_since"), int)
    return {
        "id": p["id"],
        "name": p["name"],
        "brand": text(p.get("brand")),
        "categories": text(p.get("categories")),
        "image_url": text(p.get("image_url")),
        "event_type": "product",
        "group": "product",
        "sales_since": sales if sales and len(sales) == 12 else None,
        "timestamp": integer(p.get("timestamp")),
        "frequency": integer(p.get("frequency")),
        "market": "US",
        "price": text(p.get("price")),
        "currency": "USD",
        "search_keywords": listed(p.get("search_keywords"), str),
        "keywords": listed(p.get("keywords"), str),
    }


def main() -> None:
    sample = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else None
    products = [json.loads(line) for line in (DATA / "products.jsonl").open()]
    rows = [to_row(p) for p in products[:sample]]

    name = f"productguessr_sample{sample}" if sample else "productguessr"
    path = DATA / f"{name}.parquet"
    table = pa.Table.from_pylist(rows, schema=pa.schema(CATALOG_SCHEMA))
    pq.write_table(table, path)
    print(f"wrote {len(rows)} rows -> {path.name}")

    client = UnboxAIClient(market="us")
    job = client.embed(path)
    # Save the id straight away: if waiting fails, the job may still finish.
    state = DATA / f"{name}.json"
    state.write_text(json.dumps(job.model_dump(), indent=2))
    print(f"catalog {job.catalog_id} (job {job.job_id}) -> {state.name}")

    client.catalogs.wait_for_job(job.job_id, timeout=3600, startup_grace=600)
    print("ready")


if __name__ == "__main__":
    main()
