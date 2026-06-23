"""
ВСТРОЕННЫЕ ПОВЕДЕНИЯ — конкретная игровая логика поверх rule-engine.

Это слой, который в follow.exe реализован отдельными табами/классами
(CFollowApp, CTargetDialog, CAttackTab, CLeagueMechanics, ...). У нас каждое
поведение — фабрика, возвращающая action_fn(state) -> list[InputAction]
(динамические действия) либо готовые параметры правила.

В профиле поведение подключается так:
  { "name": "...", "trigger": {...}, "behavior": "follow",
    "params": { "host_dist": 25, "step": 10 } }
"""

from __future__ import annotations

import math

from backends import InputAction
from nav import NavConfig, nav_config_from_dict, slots_to_actions
from state import GameState


# ---------------------------------------------------------------- FollowBot

def follow(params: dict):
    """Движение за лидером: если дистанция больше host_dist — шаг в его сторону.
    Аналог FollowBot: HostDist/FrontDist/Forward*/Right*. Непрерывное правило."""
    host_dist = params.get("host_dist", 25.0)

    def action_fn(s: GameState) -> list[InputAction]:
        d = s.dist_to_leader()
        if d <= host_dist:
            return []                       # уже рядом — стоим
        dx = s.leader_pos[0] - s.player_pos[0]
        dy = s.leader_pos[1] - s.player_pos[1]
        ang = math.degrees(math.atan2(dy, dx))
        return [InputAction(f"MOVE dir={ang:+.0f}° dist={d:.0f}")]

    return action_fn


# ---------------------------------------------------------------- атака

def attack(params: dict):
    """Удержание атаки, пока рядом враги (CAttackTab: 'holds right-click').
    Непрерывное правило (edge=false)."""
    key = params.get("key", "MOUSE_RIGHT")

    def action_fn(s: GameState) -> list[InputAction]:
        return [InputAction(f"HOLD {key} (attack)")] if s.enemies_near > 0 else []

    return action_fn


# ---------------------------------------------------------------- aim/target

def aim(params: dict):
    """Наведение на ближайшего врага по target_dir (CTargetDialog/Aim)."""
    key = params.get("key", "MOVE_MOUSE")

    def action_fn(s: GameState) -> list[InputAction]:
        if s.enemies_near <= 0:
            return []
        ang = math.degrees(math.atan2(s.target_dir[1], s.target_dir[0]))
        return [InputAction(f"AIM {key} dir={ang:+.0f}°")]

    return action_fn


# ---------------------------------------------------------------- авто-лут

def loot(params: dict):
    """Подбор предметов в радиусе loot_dist (AutoLoot/LootDist)."""
    loot_dist = params.get("loot_dist", 30.0)

    def action_fn(s: GameState) -> list[InputAction]:
        near = [it for it in s.items if it.get("dist", 1e9) <= loot_dist]
        near.sort(key=lambda it: it["dist"])
        return [InputAction(f"PICKUP {it['name']} ({it['dist']:.0f})") for it in near]

    return action_fn


# ---------------------------------------------------------------- on-respawn

def reactivate_auras(params: dict):
    """После респауна заново активировать ауры (COnRespawnTab)."""
    keys = params.get("auras", ["AURA1", "AURA2"])

    def action_fn(s: GameState) -> list[InputAction]:
        return [InputAction(f"CAST {k}", wait_after_ms=120) for k in keys]

    return action_fn


# ---------------------------------------------------------------- навигация

def navigate(params: dict):
    """Выполнить маршрут из NavSlot-ов (аналог NavSlot1-6 в follow.exe).

    Маршрут разворачивается в плоский список InputAction; async_run=True
    в правиле гарантирует, что навигация не блокирует остальные правила.
    Условные слоты (condition=zone_reached/portal_visible) используют
    cond_timeout_ms как задержку — StateProvider должен выставить флаг
    до истечения таймаута."""
    cfg: NavConfig = nav_config_from_dict(params)

    def action_fn(s: GameState) -> list[InputAction]:
        return slots_to_actions(cfg)

    return action_fn


# имя из JSON -> фабрика
REGISTRY = {
    "follow": follow,
    "attack": attack,
    "aim": aim,
    "loot": loot,
    "reactivate_auras": reactivate_auras,
    "navigate": navigate,
}


def build_behavior(name: str, params: dict):
    if name not in REGISTRY:
        raise ValueError(f"неизвестное поведение: {name!r}. Доступны: {list(REGISTRY)}")
    return REGISTRY[name](params or {})
