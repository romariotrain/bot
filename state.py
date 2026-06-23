"""
СОСТОЯНИЕ ИГРЫ.

Ключевое отличие "своего" бота от follow.exe: state читается ЧЕСТНО.
follow.exe слеп — он угадывает HP по цвету пикселя на экране. У нас же
GameState — это просто структура, которую в реальном проекте заполняет
твой игровой движок напрямую.

Здесь read_state() — заглушка-симулятор: HP плавно убывает и иногда
"лечится", чтобы было видно срабатывание state-правил.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field


@dataclass
class GameState:
    hp: float = 1.0            # 0.0 .. 1.0
    mana: float = 1.0          # 0.0 .. 1.0
    enemies_near: int = 0      # сколько врагов рядом
    zone: str = "town"         # текущая зона
    map_quant: int = 0         # % количества предметов на карте (для map-rolling)
    map_rarity: int = 0        # % редкости на карте

    # --- позиции (для FollowBot / Aurabot) ---
    player_pos: tuple = (0.0, 0.0)   # координаты нашего персонажа
    leader_pos: tuple = (0.0, 0.0)   # координаты лидера, за которым идём

    # --- окружение ---
    items: list = field(default_factory=list)   # лут на земле: [{"name","dist"}], для auto-loot
    target_dir: tuple = (0.0, 0.0)               # направление на ближайшего врага (для Aim)

    # --- социальные события ---
    party_invite_from: str = ""   # ник, приславший инвайт в группу
    trade_request_from: str = ""  # ник, открывший трейд

    # --- лиговый/энкаунтер-контекст (для allow/deny списков) ---
    league_mechanic: str = ""     # механика рядом: "Breach"/"Essence"/...
    altar_mod: str = ""           # мод алтаря на выбор
    encounter: str = ""           # текущий энкаунтер (для blacklist)

    just_respawned: bool = False  # флаг: только что воскресли (для On-Respawn)
    extra: dict = field(default_factory=dict)

    def dist_to_leader(self) -> float:
        dx = self.leader_pos[0] - self.player_pos[0]
        dy = self.leader_pos[1] - self.player_pos[1]
        return (dx * dx + dy * dy) ** 0.5


class StateProvider:
    """
    Источник состояния. В реальной игре подменяется на чтение из движка.
    Тут — детерминированный симулятор на синусоидах для демонстрации.
    """

    def __init__(self) -> None:
        self._t0 = time.time()

    def read(self) -> GameState:
        t = time.time() - self._t0
        # HP колеблется 0.1..1.0 с периодом ~12с — будет уходить под пороги
        hp = 0.55 + 0.45 * math.sin(t / 2.0)
        mana = 0.55 + 0.45 * math.sin(t / 3.0 + 1.0)
        # враги "появляются" волнами
        enemies = 3 if math.sin(t / 5.0) > 0.3 else 0
        zone = "map" if int(t // 20) % 2 else "town"

        # лидер ходит по кругу, мы стоим в центре -> дистанция колеблется
        leader = (40 * math.cos(t / 2.5), 40 * math.sin(t / 2.5))
        # лут периодически появляется рядом
        items = [{"name": "ChaosOrb", "dist": 18.0}] if math.sin(t / 4.0) > 0.6 else []
        # цель — туда же, где враги
        tdir = (math.cos(t), math.sin(t)) if enemies else (0.0, 0.0)

        # социальные/лиговые события — короткими импульсами
        party = "MyLeader" if 3.0 <= t % 30 < 3.4 else ""
        trade = "MyLeader" if 8.0 <= t % 30 < 8.4 else ""
        mechanic = "Essence" if 12.0 <= t % 30 < 12.4 else ""
        altar = "Take:Damage" if 16.0 <= t % 30 < 16.4 else ""
        encounter = "Ultimatum" if 20.0 <= t % 30 < 20.4 else ""
        respawned = 24.0 <= t % 30 < 24.4

        return GameState(
            hp=round(max(0.0, min(1.0, hp)), 3),
            mana=round(max(0.0, min(1.0, mana)), 3),
            enemies_near=enemies,
            zone=zone,
            player_pos=(0.0, 0.0),
            leader_pos=(round(leader[0], 1), round(leader[1], 1)),
            items=items,
            target_dir=tdir,
            party_invite_from=party,
            trade_request_from=trade,
            league_mechanic=mechanic,
            altar_mod=altar,
            encounter=encounter,
            just_respawned=respawned,
        )
