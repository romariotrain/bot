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
from maproll import MapRollConfig, maproll_config_from_dict
from nav import NavConfig, nav_config_from_dict, slots_to_actions
from state import GameState
from trade import TradeConfig, on_trade_request, trade_config_from_dict


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
    """Подбор предметов с фильтрацией по дистанции, цене уников и чёрному списку.

    Параметры (аналог AutoLoot из follow.exe):
      loot_dist  — радиус подбора в игровых единицах (default 30)
      uni_price  — минимальная цена (chaos) для подбора уников; 0 = подбирать все уники
      uni_exc    — список имён уников-исключений (blacklist), не поднимать никогда

    Каждый элемент state.items должен иметь поля:
      {"name": str, "dist": float, "rarity": str, "price": float}
    rarity: "normal" | "magic" | "rare" | "unique"
    """
    loot_dist = float(params.get("loot_dist", 30.0))
    uni_price = float(params.get("uni_price", 0.0))
    uni_exc: list[str] = [n.lower() for n in params.get("uni_exc", [])]

    def _keep(it: dict) -> bool:
        if it.get("dist", 1e9) > loot_dist:
            return False
        name = it.get("name", "").lower()
        rarity = it.get("rarity", "normal").lower()
        if rarity == "unique":
            if name in uni_exc:
                return False
            if uni_price > 0 and it.get("price", 0.0) < uni_price:
                return False
        return True

    def action_fn(s: GameState) -> list[InputAction]:
        near = [it for it in s.items if _keep(it)]
        near.sort(key=lambda it: it.get("dist", 1e9))
        return [InputAction(f"PICKUP {it['name']} ({it.get('dist', 0):.0f})") for it in near]

    return action_fn


# ---------------------------------------------------------------- on-respawn

def reactivate_auras(params: dict):
    """После респауна заново активировать ауры (COnRespawnTab)."""
    keys = params.get("auras", ["AURA1", "AURA2"])

    def action_fn(s: GameState) -> list[InputAction]:
        return [InputAction(f"CAST {k}", wait_after_ms=120) for k in keys]

    return action_fn


# ---------------------------------------------------------------- авто-трейд

def auto_trade(params: dict):
    """Принять трейд от разрешённого игрока (аналог CTradeDialog в follow.exe).

    Триггером должен быть EventTrigger на поле trade_request_from:
      {"type": "event", "field": "trade_request_from"}

    Если запрос от игрока не из whitelist — нажимает decline_key."""
    cfg: TradeConfig = trade_config_from_dict(params)

    def action_fn(s: GameState) -> list[InputAction]:
        if on_trade_request(s, cfg):
            return [InputAction(cfg.accept_key)]
        if s.trade_request_from:
            return [InputAction(cfg.decline_key)]
        return []

    return action_fn


# ---------------------------------------------------------------- авто-роллинг карты

def maproll(params: dict):
    """Откатать карту до min_quant/min_rarity.

    Возвращает action_fn, которая генерирует список клавиш одного попытки ролла.
    Итерирование «до условия» реализуется через Rule.repeat_until + Rule.max_attempts
    (задаётся в поле "reroll" JSON-профиля).

    Порядок за один цикл: prep_keys (если есть) → roll_key."""
    cfg: MapRollConfig = maproll_config_from_dict(params)

    def action_fn(s: GameState) -> list[InputAction]:
        actions = [InputAction(k, 0, cfg.gap_ms) for k in cfg.prep_keys]
        actions.append(InputAction(cfg.roll_key, 0, cfg.gap_ms))
        return actions

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
    "auto_trade": auto_trade,
    "maproll": maproll,
    "navigate": navigate,
}


def build_behavior(name: str, params: dict):
    if name not in REGISTRY:
        raise ValueError(f"неизвестное поведение: {name!r}. Доступны: {list(REGISTRY)}")
    return REGISTRY[name](params or {})
