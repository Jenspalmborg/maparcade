"""Turn each product's similar_products ranking into MapGolf's course data.

Every product keeps its 36 most similar products, in BehaviorGPT's order.
The game offers three shots per turn from bands of that ranking:
  chip    ranks 1-4     very similar, a short hop
  iron    ranks 9-18    the next shelf over
  driver  ranks 25-36   a loose match that can land far away
The game walks this graph; the map is only for drawing where you are.

Run:  uv run python scripts/build_golf.py   (after neighbours.py)
"""

import json
import random
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = 36


def main() -> None:
    data = json.loads((ROOT / "docs" / "data.json").read_text())
    index = {row[0]: i for i, row in enumerate(data["items"])}
    near = [[] for _ in data["items"]]
    for line in (ROOT / "data" / "neighbours.jsonl").open():
        row = json.loads(line)
        near[index[row["id"]]] = [index[n] for n in row["n"] if n in index][:KEEP]

    out = ROOT / "docs" / "golf.json"
    out.write_text(json.dumps({"near": near}, separators=(",", ":")))

    # Health check: hops between random playable products along these links.
    reverse = [[] for _ in near]
    for a, links in enumerate(near):
        for b in links:
            reverse[b].append(a)
    rng = random.Random(1)
    hops, unreachable = Counter(), 0
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
                hops[dist[start]] += 1
            else:
                unreachable += 1
    total = sum(hops.values()) + unreachable
    print(f"{sum(1 for n in near if n)}/{len(near)} products linked -> {out.relative_to(ROOT)} "
          f"({out.stat().st_size / 1e6:.1f} MB)")
    print(f"random pairs: {unreachable / total:.0%} unreachable; hops: "
          + ", ".join(f"{k}:{v / total:.0%}" for k, v in sorted(hops.items())))


if __name__ == "__main__":
    main()
