"""
RULE-ENGINE — ядро, перенесённое из архитектуры follow.exe.

Правило = {триггер → действие} + тайминг + humanize.
Движок в цикле опрашивает состояние, проверяет каждое правило ("пора?"),
и если да — отправляет последовательность инпутов в бэкенд.

Типы триггеров повторяют таксономию follow.exe:
  - TimedTrigger   ~ [INPUT=TIMED]   (по часам, "слепой" режим)
  - StateTrigger   ~ [INPUT=HEALTH/MANA/...]  (по состоянию игры)
  - EventTrigger   ~ [INPUT=NEWZONE] (по событию)
"""

from __future__ import annotations

import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from backends import InputAction, InputBackend
from state import GameState, StateProvider


# ---------------------------------------------------------------- триггеры

class Trigger(ABC):
    @abstractmethod
    def ready(self, now: float, state: GameState) -> bool:
        """Пора срабатывать?"""

    def reset(self) -> None:
        """Сброс при старте движка (для интервальных триггеров)."""


class TimedTrigger(Trigger):
    """Срабатывает каждые [min_ms..max_ms] (рандом в диапазоне = humanize интервала).
    Аналог Elapse=4000-4300 из профилей follow.exe."""

    def __init__(self, min_ms: int, max_ms: int) -> None:
        self.min_ms = min_ms
        self.max_ms = max_ms
        self._next = 0.0

    def _schedule(self, now: float) -> None:
        self._next = now + random.uniform(self.min_ms, self.max_ms) / 1000

    def reset(self) -> None:
        self._next = 0.0

    def ready(self, now: float, state: GameState) -> bool:
        if self._next == 0.0:
            self._schedule(now)
            return False
        if now >= self._next:
            self._schedule(now)
            return True
        return False


class StateTrigger(Trigger):
    """Срабатывает, когда предикат по состоянию истинен.
    Аналог health/mana/monster-триггеров — но по ЧЕСТНОМУ state, не по пикселям.
    edge=True → срабатывает только на переходе False→True (один раз на вход в условие)."""

    def __init__(self, predicate: Callable[[GameState], bool], edge: bool = True) -> None:
        self.predicate = predicate
        self.edge = edge
        self._was = False

    def reset(self) -> None:
        self._was = False

    def ready(self, now: float, state: GameState) -> bool:
        cur = bool(self.predicate(state))
        fire = cur and (not self._was if self.edge else True)
        self._was = cur
        return fire


class EventTrigger(Trigger):
    """Срабатывает при смене значения поля состояния (напр. zone).
    Аналог [INPUT=NEWZONE]."""

    def __init__(self, getter: Callable[[GameState], object]) -> None:
        self.getter = getter
        self._prev = object()  # заведомо отличается от первого значения

    def reset(self) -> None:
        self._prev = object()

    def ready(self, now: float, state: GameState) -> bool:
        cur = self.getter(state)
        changed = cur != self._prev
        self._prev = cur
        return changed


# ---------------------------------------------------------------- правило

@dataclass
class Rule:
    name: str
    trigger: Trigger
    actions: list[InputAction]
    gap_ms: int = 25                # пауза между клавишами в последовательности
    cooldown_ms: int = 0            # КД на само правило
    humanize_ms: int = 0            # случайная микро-задержка перед выполнением
    enabled: bool = True
    async_run: bool = False         # маршрут: крутить в своём потоке (как CreateThread у nav)
    # reroll: повторять actions, пока repeat_until(state) не станет True (как MapQuant/MapRarity)
    repeat_until: "Callable[[GameState], bool] | None" = None
    max_attempts: int = 50
    # action_fn(state) -> list[InputAction]: вычислить действия из состояния
    # (для follow/aim/loot, где инпут зависит от позиций/целей, а не статичен)
    action_fn: "Callable[[GameState], list[InputAction]] | None" = None
    _last_fire: float = field(default=0.0, repr=False)
    _running: bool = field(default=False, repr=False)  # маршрут/реролл идёт?

    def on_cooldown(self, now: float) -> bool:
        return self.cooldown_ms > 0 and (now - self._last_fire) * 1000 < self.cooldown_ms

    def fire(self, now: float, backend: InputBackend, should_stop=None, read_state=None) -> None:
        self._last_fire = now
        if self.async_run:
            # длинный сценарий (маршрут/реролл): отдельный поток, не блокирует фласки
            if self._running:
                return                       # уже идём — не перезапускаем
            self._running = True
            t = threading.Thread(
                target=self._run, args=(backend, should_stop, read_state), daemon=True)
            t.start()
        else:
            self._run(backend, should_stop, read_state)

    def _run(self, backend: InputBackend, should_stop, read_state) -> None:
        try:
            if self.humanize_ms:
                time.sleep(random.uniform(0, self.humanize_ms) / 1000)
            if self.repeat_until is not None:
                self._run_reroll(backend, should_stop, read_state)
            else:
                # динамические действия (follow/aim/loot) или статичные (фласки/комбо)
                actions = self.action_fn(read_state()) if (self.action_fn and read_state) \
                    else self.actions
                backend.send_sequence(actions, gap_ms=self.gap_ms, should_stop=should_stop)
        finally:
            self._running = False

    def _run_reroll(self, backend: InputBackend, should_stop, read_state) -> None:
        """Повторять actions, пока критерий не выполнен либо не кончились попытки."""
        for attempt in range(1, self.max_attempts + 1):
            if should_stop and should_stop():
                return
            if read_state and self.repeat_until(read_state()):
                return                       # критерий уже выполнен
            backend.send_sequence(self.actions, gap_ms=self.gap_ms, should_stop=should_stop)
        # попытки исчерпаны — выходим (в реальном боте тут лог "не удалось зароллить")


# ---------------------------------------------------------------- движок

class Engine:
    """Крутит правила в отдельном потоке. tick_ms — частота опроса (как SetTimer)."""

    def __init__(
        self,
        backend: InputBackend,
        provider: StateProvider,
        rules: list[Rule],
        tick_ms: int = 50,
    ) -> None:
        self.backend = backend
        self.provider = provider
        self.rules = rules
        self.tick_ms = tick_ms
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        for r in self.rules:
            r.trigger.reset()
            r._running = False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[engine] started, {len(self.rules)} rules, tick={self.tick_ms}ms")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        print("[engine] stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            state = self.provider.read()          # ЧЕСТНОЕ состояние (не пиксели)
            for rule in self.rules:
                if not rule.enabled or rule.on_cooldown(now):
                    continue
                if rule.trigger.ready(now, state):
                    rule.fire(now, self.backend,
                              should_stop=self._stop.is_set,
                              read_state=self.provider.read)
            time.sleep(self.tick_ms / 1000)
