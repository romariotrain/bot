"""
NAV — навигационный маршрут из до 6 слотов (аналог NavSlot1-6 из follow.exe).

NavSlot задаёт один шаг: нажать клавишу, подождать, опционально проверить
условие (zone_reached / portal_visible) прежде чем перейти к следующему шагу.
NavConfig собирает слоты в маршрут с опцией зацикливания.

Использование в профиле:
  {
    "behavior": "navigate",
    "params": {
      "slots": [
        {"key": "W", "hold_ms": 500, "wait_after_ms": 200},
        {"key": "E", "condition": "portal_visible", "cond_timeout_ms": 3000},
        {"key": "T", "wait_after_ms": 1000, "condition": "zone_reached"}
      ],
      "loop": false
    }
  }
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NavSlot:
    """Один шаг маршрута навигации."""
    key: str                    # клавиша или действие; "" = только ждать
    hold_ms: int = 0            # время удержания клавиши
    wait_after_ms: int = 200    # пауза после отпускания (между шагами)
    condition: str = ""         # "" | "zone_reached" | "portal_visible"
    cond_timeout_ms: int = 5000 # максимальное ожидание условия перед следующим шагом


@dataclass
class NavConfig:
    """Полный маршрут навигации (до 6 слотов, как в follow.exe)."""
    slots: list[NavSlot] = field(default_factory=list)
    loop: bool = False          # повторять маршрут после последнего слота


def nav_config_from_dict(d: dict) -> NavConfig:
    """Собрать NavConfig из словаря (из JSON-профиля)."""
    slots = [
        NavSlot(
            key             = s.get("key", ""),
            hold_ms         = s.get("hold_ms", 0),
            wait_after_ms   = s.get("wait_after_ms", 200),
            condition       = s.get("condition", ""),
            cond_timeout_ms = s.get("cond_timeout_ms", 5000),
        )
        for s in d.get("slots", [])
    ]
    return NavConfig(slots=slots, loop=d.get("loop", False))


def slots_to_actions(cfg: NavConfig) -> "list[InputAction]":
    """Развернуть NavConfig в плоский список InputAction для отправки в backend.

    Условные слоты (condition != "") используют cond_timeout_ms как wait_after_ms —
    фактическая проверка условия должна быть в StateProvider перед запуском."""
    from backends import InputAction
    actions = []
    for slot in cfg.slots:
        if not slot.key:
            continue
        wait = slot.cond_timeout_ms if slot.condition else slot.wait_after_ms
        actions.append(InputAction(slot.key, slot.hold_ms, wait))
    return actions
