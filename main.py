"""
Демо-запуск rule-engine.

Что показывает:
  - TimedTrigger  : утилити-скилл по таймеру (как [INPUT=TIMED])
  - StateTrigger  : лайф-фласк, когда hp < 35% (как health-триггер, но по честному state)
  - StateTrigger  : мана-фласк, когда mana < 30%
  - EventTrigger  : действие при смене зоны (как [INPUT=NEWZONE])

Аварийный стоп: Ctrl+C (аналог клавиши End в follow.exe, который через
GetAsyncKeyState(0x23) гасит поток ввода).

Запуск:
  python3 main.py                      # правила из кода (build_rules)
  python3 main.py profiles/demo.json   # правила из JSON-профиля
"""

from __future__ import annotations

import sys
import time

from backends import InputAction, LogBackend
from engine import Engine, EventTrigger, Rule, StateTrigger, TimedTrigger
from profiles import load_profile
from state import StateProvider


def build_rules() -> list[Rule]:
    return [
        Rule(
            name="utility-skill (timed)",
            trigger=TimedTrigger(min_ms=4000, max_ms=4300),
            actions=[InputAction("X")],
            humanize_ms=40,
        ),
        Rule(
            name="life-flask @ hp<35%",
            trigger=StateTrigger(lambda s: s.hp < 0.35, edge=True),
            actions=[InputAction("1")],
            cooldown_ms=3000,
        ),
        Rule(
            name="mana-flask @ mana<30%",
            trigger=StateTrigger(lambda s: s.mana < 0.30, edge=True),
            actions=[InputAction("2")],
            cooldown_ms=3000,
        ),
        Rule(
            name="on-new-zone combo",
            trigger=EventTrigger(lambda s: s.zone),
            actions=[InputAction("Q"), InputAction("W"), InputAction("E")],
            gap_ms=60,
        ),
    ]


def main() -> None:
    backend = LogBackend()          # на Windows заменить на SendInputBackend
    provider = StateProvider()      # в своей игре — чтение из движка

    if len(sys.argv) > 1:
        rules, tick_ms = load_profile(sys.argv[1])
        print(f"загружен профиль: {sys.argv[1]} ({len(rules)} правил)")
    else:
        rules, tick_ms = build_rules(), 50

    engine = Engine(backend, provider, rules, tick_ms=tick_ms)

    engine.start()
    print("Работает. Ctrl+C — аварийный стоп.\n")
    try:
        while True:
            st = provider.read()
            print(f"  state: hp={st.hp:.2f} mana={st.mana:.2f} "
                  f"enemies={st.enemies_near} zone={st.zone}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] аварийный стоп")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
