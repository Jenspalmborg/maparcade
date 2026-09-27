"""Turn each product's similar_products ranking into MapGolf clubs.

Each product gets six shots, all picked from BehaviorGPT's own ranking of
the products most similar to it:
  putter  ranks 1 and 2    tiny, safe steps
  iron    ranks 10 and 18  the next shelf over
  driver  ranks 40 and 56  long shots that can reach another aisle
The game walks this graph; the map is only for drawing where you are.

Run:  uv run python scripts/build_golf.py   (after neighbours.py)
"""

import json
import random
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANKS = [0, 1, 9, 17, 39, 55]


def main() -> None:
    data = json.loads((ROOT / "docs" / "data.json").read_text())
    index = {row[0]: i for i, row in enumerate(data["items"])}
    ranked = {}
    for line in (ROOT / "data" / "neighbours.jsonl").open():
        row = json.loads(line)
        ranked[row["id"]] = [index[n] for n in row["n"] if n in index]

    clubs = []
    for row in data["items"]:
        near = ranked.get(row[0], [])
        # Short lists fall back to the furthest neighbour available.
        clubs.append([near[min(r, len(near) - 1)] if near else -1 for r in RANKS])

    out = ROOT / "docs" / "golf.json"
    out.write_text(json.dumps({"ranks": RANKS, "clubs": clubs}, separators=(",", ":")))

    # Health check: how far apart are playable products in this graph?
    n = len(clubs)
    reverse = [[] for _ in range(n)]
    for a, shots in enumerate(clubs):
        for b in shots:
            if b >= 0:
                reverse[b].append(a)
    rng = random.Random(1)
    lengths, unreachable = Counter(), 0
    for goal in rng.sample(data["pool"], 60):
        dist = {goal: 0}
        queue = deque([goal])
        while queue:
            v = queue.popleft()
            for u in reverse[v]:
                if u not in dist:
                    dist[u] = dist[v] + 1
                    queue.append(u)
        for start in rng.sample(data["pool"], 60):
            if start in dist:
                lengths[dist[start]] += 1
            else:
                unreachable += 1
    total = sum(lengths.values()) + unreachable
    print(f"{sum(1 for c in clubs if c[0] >= 0)}/{n} products have clubs -> {out.relative_to(ROOT)} "
          f"({out.stat().st_size / 1e3:.0f} kB)")
    print(f"random pairs: {unreachable / total:.0%} unreachable; shots needed: "
          + ", ".join(f"{k}:{v / total:.0%}" for k, v in sorted(lengths.items())))


if __name__ == "__main__":
    main()
