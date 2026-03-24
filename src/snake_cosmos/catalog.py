from __future__ import annotations

from dataclasses import dataclass
import json
from importlib import resources


@dataclass(frozen=True)
class FoodDefinition:
    food_id: str
    label: str
    short_label: str
    rarity: str
    score: int
    growth: int
    sprint_gain: float
    spawn_weight: float
    color: tuple[int, int, int]
    glow_color: tuple[int, int, int]


@dataclass(frozen=True)
class ItemDefinition:
    item_id: str
    label: str
    short_label: str
    description: str
    duration: float
    spawn_weight: float
    effect_type: str
    value: float
    instant_sprint: float
    icon_id: str
    color: tuple[int, int, int]
    glow_color: tuple[int, int, int]


def _load_json(name: str) -> list[dict]:
    with resources.files("snake_cosmos.content").joinpath(name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_food_definitions() -> dict[str, FoodDefinition]:
    entries = _load_json("foods.json")
    return {
        entry["id"]: FoodDefinition(
            food_id=entry["id"],
            label=entry["label"],
            short_label=entry.get("short_label", entry["label"]),
            rarity=entry["rarity"],
            score=entry["score"],
            growth=entry["growth"],
            sprint_gain=entry["sprint_gain"],
            spawn_weight=entry["spawn_weight"],
            color=tuple(entry["color"]),
            glow_color=tuple(entry["glow_color"]),
        )
        for entry in entries
    }


def load_item_definitions() -> dict[str, ItemDefinition]:
    entries = _load_json("items.json")
    return {
        entry["id"]: ItemDefinition(
            item_id=entry["id"],
            label=entry["label"],
            short_label=entry.get("short_label", entry["label"]),
            description=entry["description"],
            duration=entry["duration"],
            spawn_weight=entry["spawn_weight"],
            effect_type=entry["effect_type"],
            value=entry["value"],
            instant_sprint=entry["instant_sprint"],
            icon_id=entry.get("icon_id", "orb"),
            color=tuple(entry["color"]),
            glow_color=tuple(entry["glow_color"]),
        )
        for entry in entries
    }
