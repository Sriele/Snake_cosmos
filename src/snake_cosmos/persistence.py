from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from snake_cosmos.core import Settings


SAVE_PATH = Path(".snake_cosmos_save.json")


def load_save() -> tuple[int, Settings]:
    if not SAVE_PATH.exists():
        return 0, Settings()
    try:
        data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        settings_data = data.get("settings", {})
        return int(data.get("best_score", 0)), Settings(
            master_volume=float(settings_data.get("master_volume", 0.8)),
            music_volume=float(settings_data.get("music_volume", 0.55)),
            sfx_volume=float(settings_data.get("sfx_volume", 0.8)),
            fullscreen=bool(settings_data.get("fullscreen", False)),
            screen_shake=float(settings_data.get("screen_shake", 0.6)),
            keybinds=dict(settings_data.get("keybinds", Settings().keybinds)),
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0, Settings()


def save_state(best_score: int, settings: Settings) -> None:
    payload = {
        "best_score": best_score,
        "settings": asdict(settings),
    }
    SAVE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
