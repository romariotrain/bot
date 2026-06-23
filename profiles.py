"""
ПРОФИЛИ — декларативное описание правил в JSON (Фаза 3).

Аналог Profiles\\*.txt в follow.exe, только формат удобнее (JSON вместо INI).
Профиль описывает правила данными, без кода — поэтому их можно
редактировать руками или будущим GUI и не трогать движок.

Схема правила:
  {
    "name": "...",
    "trigger": { ... },          # см. build_trigger ниже
    "actions": ["X", "1", ...],  # или [{"key":"R","hold_ms":200}]
    "gap_ms": 25, "cooldown_ms": 0, "humanize_ms": 0, "enabled": true
  }

Триггеры:
  {"type":"timed", "min_ms":4000, "max_ms":4300}
  {"type":"state", "field":"hp", "op":"<", "value":0.35, "edge":true}
  {"type":"event", "field":"zone"}
"""

from __future__ import annotations

import json
import operator
from pathlib import Path

from backends import InputAction
from behaviors import build_behavior
from engine import DistanceTrigger, EventTrigger, Rule, StateTrigger, TimedTrigger, Trigger

_OPS = {
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}


def build_condition(cfg: dict):
    """Строит предикат state -> bool из декларативного описания.

    Поддерживает простое условие {field, op, value} и составные:
      {"all": [cond, cond, ...]}  — AND
      {"any": [cond, cond, ...]}  — OR
    Это аналог правил follow.exe, зависящих сразу от нескольких условий.
    """
    if "all" in cfg:
        subs = [build_condition(c) for c in cfg["all"]]
        return lambda s, subs=subs: all(p(s) for p in subs)
    if "any" in cfg:
        subs = [build_condition(c) for c in cfg["any"]]
        return lambda s, subs=subs: any(p(s) for p in subs)
    field, opname, value = cfg["field"], cfg["op"], cfg["value"]
    if opname == "in":        # allow-list: значение поля входит в список
        return lambda s, field=field, value=value: getattr(s, field) in value
    if opname == "not_in":    # deny/blacklist: значения нет в списке
        return lambda s, field=field, value=value: getattr(s, field) not in value
    op = _OPS[opname]
    return lambda s, field=field, op=op, value=value: op(getattr(s, field), value)


def build_trigger(cfg: dict) -> Trigger:
    t = cfg["type"]
    if t == "timed":
        return TimedTrigger(cfg["min_ms"], cfg["max_ms"])
    if t == "state":
        return StateTrigger(build_condition(cfg), edge=cfg.get("edge", True))
    if t == "event":
        field = cfg["field"]
        return EventTrigger(lambda s, field=field: getattr(s, field))
    if t == "distance":
        return DistanceTrigger(
            forward_min=cfg.get("forward_min", -450),
            forward_max=cfg.get("forward_max",  450),
            right_min  =cfg.get("right_min",   -450),
            right_max  =cfg.get("right_max",    450),
            edge       =cfg.get("edge", True),
        )
    raise ValueError(f"неизвестный тип триггера: {t!r}")


def build_action(a) -> InputAction:
    if isinstance(a, str):
        return InputAction(a)
    return InputAction(a["key"], a.get("hold_ms", 0), a.get("wait_after_ms", 0))


def build_rule(cfg: dict) -> Rule:
    reroll = cfg.get("reroll")
    behavior = cfg.get("behavior")
    return Rule(
        name=cfg["name"],
        trigger=build_trigger(cfg["trigger"]),
        actions=[build_action(a) for a in cfg.get("actions", [])],
        action_fn=build_behavior(behavior, cfg.get("params")) if behavior else None,
        gap_ms=cfg.get("gap_ms", 25),
        cooldown_ms=cfg.get("cooldown_ms", 0),
        humanize_ms=cfg.get("humanize_ms", 0),
        enabled=cfg.get("enabled", True),
        async_run=cfg.get("async_run", False),
        repeat_until=build_condition(reroll["until"]) if reroll else None,
        max_attempts=reroll.get("max_attempts", 50) if reroll else 50,
    )


def load_profile(path: str | Path) -> tuple[list[Rule], int]:
    """Вернёт (rules, tick_ms)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = [build_rule(r) for r in data.get("rules", [])]
    return rules, data.get("tick_ms", 50)
