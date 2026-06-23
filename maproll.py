"""
MAPROLL — авто-роллинг карты до нужных характеристик (аналог MapRoll из follow.exe).

MapRollConfig задаёт цель: минимальный % quantity и rarity.
map_roll_done(state, cfg) — предикат «карта уже достаточно хороша».

Использование в профиле (с механикой reroll из engine.Rule):
  {
    "name": "roll map",
    "trigger": {"type": "event", "field": "zone"},
    "behavior": "maproll",
    "params": {
      "min_quant": 80,
      "min_rarity": 60,
      "roll_key": "CHAOS_ORB",
      "prep_keys": ["SCOUR", "ALCHEMY"]
    },
    "async_run": true,
    "reroll": {
      "until": {"field": "map_quant", "op": ">=", "value": 80},
      "max_attempts": 30
    }
  }

Заметка: движок Rule._run_reroll повторяет actions (roll_key) до тех пор пока
repeat_until(state) не вернёт True или не кончатся попытки.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MapRollConfig:
    """Целевые характеристики карты."""
    min_quant: int = 0          # минимальный % quantity
    min_rarity: int = 0         # минимальный % rarity
    roll_key: str = "CHAOS_ORB" # клавиша одного ролла (Chaos Orb на карте)
    prep_keys: list[str] = field(default_factory=list)  # подготовительные шаги (Scour→Alch)
    gap_ms: int = 500           # пауза между нажатиями внутри одной попытки


def map_roll_done(state: "GameState", cfg: MapRollConfig) -> bool:  # noqa: F821
    """Вернуть True если карта уже отвечает требованиям cfg."""
    return state.map_quant >= cfg.min_quant and state.map_rarity >= cfg.min_rarity


def maproll_config_from_dict(d: dict) -> MapRollConfig:
    return MapRollConfig(
        min_quant  = d.get("min_quant", 0),
        min_rarity = d.get("min_rarity", 0),
        roll_key   = d.get("roll_key", "CHAOS_ORB"),
        prep_keys  = d.get("prep_keys", []),
        gap_ms     = d.get("gap_ms", 500),
    )
