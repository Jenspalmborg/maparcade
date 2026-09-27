"""Fetch the catalog's map and write the game's data file.

BehaviorGPT's umap endpoint returns a finished Plotly page. The point
coordinates are pulled out of it (as in Unbox-AI/aic-artworks), joined with the
product fields, and written to docs/data.json. The game itself never calls the
API, so the site can be hosted anywhere without a key.

Run:  uv run python scripts/build_map.py [data/productguessr.json]
"""

import base64
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from behaviorgpt import UnboxAIClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "docs"
load_dotenv(ROOT / ".env")

# Top-level categories folded into a handful of colour families.
FAMILIES = [
    ("Home & Garden", ["Home", "Patio", "Tools", "Kitchen", "Cooking", "Furniture", "Garden", "Appliances"]),
    ("Tech", ["Electronics", "Cell Phones", "Mobile Phones", "PC", "Computers", "Camera"]),
    ("Fashion", ["Clothing", "Accessories", "Men", "Women", "Shoes", "Jewelry", "Luggage", "Girls", "Boys"]),
    ("Food & Drink", ["Grocery", "Food", "Beverages"]),
    ("Beauty & Health", ["Beauty", "Health", "Personal Care"]),
    ("Toys & Games", ["Toys", "Video Games", "Games"]),
    ("Sports & Outdoors", ["Sports", "Outdoor", "Exercise"]),
    ("Office & Books", ["Office", "Books", "Kindle"]),
    ("Music & Crafts", ["Musical", "Arts", "Crafts", "Sewing"]),
    ("Pets", ["Pet", "Cats", "Dogs"]),
    ("Baby", ["Baby"]),
    ("Automotive", ["Automotive", "Car"]),
]
OTHER = len(FAMILIES)

STOP = set("""a an and the for with of in on to by from or at as is it its your you our
new set pack pcs pc piece pieces count ct oz fl lb inch inches cm mm size sizes small medium
large xl 2xl 3xl women womens men mens kids adult unisex girls boys black white blue red
green pink gray grey color colors gift gifts 1 2 3 4 5 6 8 10 12 16 20 24 30 50 100 x
premium best original compatible portable home kit professional perfect heavy duty
smart unlocked code playing digital""".split())


def family(categories: str | None) -> int:
    first = (categories or "").split(",")[0].strip()
    for i, (_, keys) in enumerate(FAMILIES):
        if any(first.startswith(k) for k in keys):
            return i
    return OTHER


def _array(values) -> np.ndarray:
    """Plotly stores long arrays as base64 typed arrays: {"dtype", "bdata"}."""
    if isinstance(values, dict):
        raw = base64.b64decode(values["bdata"])
        return np.frombuffer(raw, dtype=np.dtype(values["dtype"])).astype(float)
    return np.asarray(values, dtype=float)


def umap_points(html: str) -> dict[str, tuple[float, float]]:
    start = html.index("[", html.index("Plotly.newPlot("))
    traces, _ = json.JSONDecoder().raw_decode(html, start)
    points = {}
    for trace in traces:
        xs, ys = _array(trace["x"]), _array(trace["y"])
        for row, x, y in zip(trace["customdata"], xs, ys):
            points[str(row[-1])] = (float(x), float(y))
    return points


def words(name: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z][a-z'-]{2,}", name.lower())
        if w not in STOP and not w.endswith("'s")
    }


def landmarks(items: list[dict], grid: int = 18, per_cell: int = 2) -> list[dict]:
    """A word per map region that is much more common there than elsewhere."""
    total = Counter(w for it in items for w in words(it["name"]))
    n = len(items)
    cells: dict[tuple[int, int], list[dict]] = {}
    for it in items:
        key = (min(int(it["x"] * grid), grid - 1), min(int(it["y"] * grid), grid - 1))
        cells.setdefault(key, []).append(it)

    labels, used = [], set()
    for members in cells.values():
        if len(members) < 18:
            continue
        local = Counter(w for it in members for w in words(it["name"]))
        scored = []
        for w, c in local.items():
            if c < 5 or w in used:
                continue
            lift = (c / len(members)) / (total[w] / n)
            scored.append((c * math.log(lift + 1), w))
        for _, w in sorted(scored, reverse=True)[:per_cell]:
            hits = [it for it in members if w in words(it["name"])]
            labels.append({
                "t": w,
                "x": round(sum(h["x"] for h in hits) / len(hits), 4),
                "y": round(sum(h["y"] for h in hits) / len(hits), 4),
                "n": len(hits),
            })
            used.add(w)
    return sorted(labels, key=lambda label: -label["n"])


def main() -> None:
    state = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "productguessr.json"
    catalog_id = json.loads(state.read_text())["catalog_id"]

    cache = DATA / f"umap_{catalog_id}.html"
    if not cache.exists():
        cache.write_text(UnboxAIClient(market="us").umap(catalog_id=catalog_id))
    points = umap_points(cache.read_text())

    products = {}
    for line in (DATA / "products.jsonl").open():
        p = json.loads(line)
        products[p["id"]] = p

    xs = np.array([x for x, _ in points.values()])
    ys = np.array([y for _, y in points.values()])
    # One scale for both axes keeps distances honest; centre the shorter side.
    span = max(np.ptp(xs), np.ptp(ys))
    x0 = xs.min() - (span - np.ptp(xs)) / 2
    y0 = ys.min() - (span - np.ptp(ys)) / 2

    items = []
    for pid, (x, y) in points.items():
        p = products.get(pid)
        if not p:
            continue
        try:
            price = round(float(p.get("price")), 2)
        except (TypeError, ValueError):
            price = None
        freq = int(float(p.get("frequency") or 0)) if str(p.get("frequency")) != "None" else 0
        items.append({
            "id": pid,
            "name": p["name"].strip(),
            "img": p["image_url"],
            "price": price,
            "f": family(p.get("categories")),
            "x": round((x - x0) / span, 4),
            # Screen y grows downwards; flip so the map matches the Plotly view.
            "y": round(1 - (y - y0) / span, 4),
            "freq": freq,
        })

    # The map packs similar products onto the exact same spot. Fan each stack
    # out in a small sunflower spiral so every product gets its own dot.
    stacks: dict[tuple[int, int], list[dict]] = {}
    for it in items:
        stacks.setdefault((round(it["x"] / 0.002), round(it["y"] / 0.002)), []).append(it)
    golden = math.pi * (3 - math.sqrt(5))
    for stack in stacks.values():
        for k, it in enumerate(stack[1:], start=1):
            r = 0.0022 * math.sqrt(k)
            it["x"] = round(it["x"] + r * math.cos(k * golden), 4)
            it["y"] = round(it["y"] + r * math.sin(k * golden), 4)

    # Rounds use recognisable products: popular, with a descriptive title.
    freqs = sorted(it["freq"] for it in items)
    cutoff = freqs[len(freqs) // 3]
    pool = [
        i for i, it in enumerate(items)
        if it["freq"] >= cutoff and len(it["name"].split()) >= 3 and it["f"] != OTHER
    ]

    out = {
        "families": [name for name, _ in FAMILIES] + ["Other"],
        # Columns instead of objects keep the file small.
        "cols": ["id", "name", "img", "price", "f", "x", "y"],
        "items": [[it[c] for c in ("id", "name", "img", "price", "f", "x", "y")] for it in items],
        "pool": pool,
        "labels": landmarks(items),
    }
    SITE.mkdir(exist_ok=True)
    path = SITE / "data.json"
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(items)} points, {len(pool)} playable, {len(out['labels'])} landmarks, "
          f"{path.stat().st_size / 1e6:.1f} MB -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
