"""Collect a varied set of products from the pre-embedded retail catalog.

The pre-embedded catalogs have no map, so we copy a few thousand products into
a catalog of our own (see embed.py) and ask for its map there.

Products come from two sources: the cold-start ranking (most popular first) and
a spread of searches across everyday shopping areas, so the map has many
distinct neighbourhoods rather than one big blob of bestsellers.

Run:  uv run python scripts/harvest.py
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from behaviorgpt import Search, UnboxAIClient
from behaviorgpt._exceptions import UnboxAIError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "products.jsonl"
load_dotenv(ROOT / ".env")

client = UnboxAIClient(market="us", default_catalog_id="retail_catalog")

QUERIES = """
running shoes, hiking boots, yoga mat, dumbbells, bicycle helmet, tennis racket, golf balls,
camping tent, sleeping bag, fishing rod, kayak paddle, ski goggles, swimming goggles, jump rope,
espresso machine, coffee beans, tea kettle, chef knife, cast iron skillet, blender, air fryer,
baking pans, cutting board, spice rack, wine glasses, cocktail shaker, lunch box, water bottle,
sofa pillow, throw blanket, scented candle, wall clock, picture frame, table lamp, bedsheets,
bath towels, shower curtain, storage bins, vacuum cleaner, air purifier, houseplant pot,
garden hose, pruning shears, bird feeder, grill tools, patio lights, lawn mower,
lipstick, face moisturizer, shampoo, perfume, nail polish, hair dryer, makeup brushes, sunscreen,
electric toothbrush, razor, beard oil, vitamins, protein powder, massage gun,
headphones, bluetooth speaker, phone case, laptop stand, mechanical keyboard, gaming mouse,
smart watch, webcam, usb charger, power bank, tablet, e-reader, drone, security camera,
video game controller, nintendo switch game, board game, jigsaw puzzle, lego set, playing cards,
stuffed animal, baby stroller, baby bottles, diapers, kids art supplies, toy car, doll house,
dog food, cat toy, dog leash, aquarium, bird cage,
womens dress, mens jeans, winter jacket, leather jacket, hoodie, sneakers, sandals, socks,
underwear, swimsuit, sunglasses, handbag, backpack, wallet, watch, necklace, earrings, hat, scarf,
notebook, fountain pen, desk organizer, printer paper, sticky notes, calculator, planner,
acoustic guitar, ukulele, piano keyboard, drum sticks, vinyl record, microphone,
paint brushes, sewing machine, knitting yarn, craft glue, sketchbook,
car phone mount, car vacuum, tire inflator, motor oil, bike lights,
snacks, chocolate, candy, pasta, olive oil, hot sauce, cereal, energy drink, sparkling water,
cookbook, novel, childrens book, travel pillow, suitcase, umbrella, party balloons, gift wrap
"""


def rows(items) -> list[dict]:
    return [dict(i.data, id=i.id) for i in items]


def search(query: str) -> list[dict]:
    try:
        res = client.complete(history=[Search(query)], limit=60)
    except UnboxAIError as exc:
        print(f"  skip {query!r}: {exc}")
        return []
    return rows(res.products.items)


def popular(offset: int) -> list[dict]:
    try:
        return rows(client.complete(history=[], limit=100, offset=offset).products.items)
    except UnboxAIError:
        return []


def main() -> None:
    queries = [q.strip() for q in QUERIES.replace("\n", " ").split(",") if q.strip()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        batches = list(pool.map(search, queries))
        batches += list(pool.map(popular, range(0, 3000, 100)))

    seen_ids, seen_titles, kept = set(), set(), []
    for batch in batches:
        for p in batch:
            name = (p.get("name") or "").strip()
            image = p.get("image_url") or ""
            # Near-identical variants ("Nike Men's Retro" x 20) would stack on one
            # spot and make rounds repetitive; keep the first of each title stem.
            title = " ".join(name.lower().split()[:5])
            if not name or not image.startswith("https://"):
                continue
            if p["id"] in seen_ids or title in seen_titles:
                continue
            seen_ids.add(p["id"])
            seen_titles.add(title)
            kept.append(p)

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as f:
        for p in kept:
            f.write(json.dumps(p) + "\n")
    print(f"{len(queries)} queries -> {len(kept)} unique products -> {OUT}")


if __name__ == "__main__":
    main()
