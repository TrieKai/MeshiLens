"""Small Traditional-Chinese presentation helpers for public Tabelog labels."""

from __future__ import annotations

from functools import cache
from importlib.resources import files
import json
import re
from typing import Any

# gurume cuts Tabelog's access text at the first 駅, so `各線「渋谷駅」ハチ公口`
# arrives as `各線「渋谷駅`; the closing bracket cannot be required.
QUOTED_STATION_RE = re.compile(r"[「『]([^」』]+)")
LINE_QUALIFIED_STATION_RE = re.compile(
    r"^(?:(?:JR|東京メトロ|都営(?:地下鉄)?|東急|京王|京急|小田急|西武|東武|相鉄|京成)[^「『]*線)(.+?駅?)$"
)


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


def station_name(value: Any) -> str:
    """Extract the station name from line-qualified labels such as `JR山手線大塚駅`."""
    station = str(value or "").strip()
    quoted = QUOTED_STATION_RE.search(station)
    if quoted:
        return quoted.group(1).strip()
    line_qualified = LINE_QUALIFIED_STATION_RE.match(station)
    return line_qualified.group(1).strip() if line_qualified else station
