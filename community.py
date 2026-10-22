# community.py — offline cache of approved community ideas (community.json).
#
# Items are exactly what the Apps Script feed returns:
#   {"id": 3, "text": "...", "name": "Blake", "time": "afternoon",
#    "does": ["show"], "vibe": ["silly"]}
# The newest COMMUNITY_MAX are kept, so ideas survive reboots and offline time,
# and as_idea() turns them into ideas.json format for the inspire matcher.

import json
import config as C


def load():
    try:
        with open(C.COMMUNITY_FILE) as f:
            items = json.load(f)
        return [i for i in items if isinstance(i, dict) and "id" in i] if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def save(items):
    try:
        with open(C.COMMUNITY_FILE, "w") as f:
            json.dump(items, f)
    except OSError as e:
        print("community: save failed", e)


def merge(items, new):
    """Add feed items to `items` in place (dedupe by id, keep the newest
    COMMUNITY_MAX, ordered by id). Returns the items that were actually new."""
    have = set(i["id"] for i in items)
    added = []
    for n in new:
        if not isinstance(n, dict) or not isinstance(n.get("id"), int):
            continue
        if n["id"] in have or not str(n.get("text", "")).strip():
            continue
        have.add(n["id"])
        added.append(n)
    if added:
        items.extend(added)
        items.sort(key=lambda i: i["id"])
        del items[:-C.COMMUNITY_MAX]
    return added


def find(items, iid):
    for i in items:
        if i["id"] == iid:
            return i
    return None


def title(item):
    name = str(item.get("name") or "").strip()
    return ("From " + name)[:16] if name else "Community idea"


def as_idea(item):
    """ideas.json format. parts ["?"] keeps community ideas out of the
    "My desk only" filter, since we don't know what parts they need."""
    return {
        "id": "c{}".format(item["id"]),
        "title": title(item),
        "text": str(item.get("text", "")),
        "time": item.get("time", ""),
        "does": item.get("does") or [],
        "vibe": item.get("vibe") or [],
        "parts": ["?"],
        "source": "community",
    }
