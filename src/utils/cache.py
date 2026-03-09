import json
import os
import hashlib
from typing import List, Set

CACHE_FILE = "ideas_cache.json"

def get_hash(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

def load_cache() -> Set[str]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_to_cache(titles: List[str]):
    cache = load_cache()
    for t in titles:
        cache.add(get_hash(t))
    with open(CACHE_FILE, "w") as f:
        json.dump(list(cache), f)

def is_duplicate(title: str, cache: Set[str]) -> bool:
    return get_hash(title) in cache
