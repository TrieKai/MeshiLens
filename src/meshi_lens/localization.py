"""Small Traditional-Chinese presentation helpers for public Tabelog labels."""

from __future__ import annotations

from functools import cache
from importlib.resources import files
import json
from typing import Any

@cache
def tabelog_genre_zh_hant_map() -> dict[str, str]:
    """Load the editable cuisine-label mapping bundled with MeshiLens."""
    try:
        payload = json.loads(
            files("meshi_lens")
            .joinpath("data/tabelog-genres-zh-hant.json")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(source): str(target)
        for source, target in payload.items()
        if str(source).strip() and str(target).strip()
    }


def tabelog_label_zh_hant(value: Any) -> str:
    """Translate well-known Tabelog cuisine labels while preserving unknown names."""
    label = str(value or "").strip()
    if not label:
        return ""
    translations = tabelog_genre_zh_hant_map()
    for source in sorted(translations, key=len, reverse=True):
        label = label.replace(source, translations[source])
    return label


def tabelog_station_zh_hant(value: Any) -> str:
    """Use the Traditional-Chinese station suffix while retaining the station name."""
    return str(value or "").strip().replace("駅", "站")
