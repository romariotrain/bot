"""
Слой ВВОДА.

Абстракция над "как нажать клавишу". У движка единый интерфейс send(),
а конкретный способ доставки подменяется. Ровно так же устроен follow.exe:
там бэкенды — ViGEmBus / Interception / SendInput, и движок не знает, какой
именно активен.

Здесь:
  - LogBackend     — ничего не нажимает, печатает. Работает везде (в т.ч. macOS).
                     Идеален, чтобы видеть логику движка.
  - SendInputBackend (заглушка) — пример, как подключить настоящий ввод на Windows.
"""

from __future__ import annotations

import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InputAction:
    """Одно элементарное действие ввода: нажать (и отпустить) клавишу.

    wait_after_ms нужен для маршрутов навигации (NavSlot): между шагами
    "дойти до точки", "подождать", "кликнуть портал" задержки разные, поэтому
    они задаются на каждый шаг отдельно, а не общим gap_ms."""
    key: str                # "W", "X", "MOUSE_RIGHT", ...
    hold_ms: int = 0        # сколько держать перед отпусканием (0 = тап)
    wait_after_ms: int = 0  # пауза ПОСЛЕ шага (для маршрутов); 0 = взять общий gap_ms


class InputBackend(ABC):
    """Контракт любого способа доставки ввода."""

    @abstractmethod
    def send(self, action: InputAction) -> None: ...

    def send_sequence(
        self,
        actions: list[InputAction],
        gap_ms: int = 0,
        should_stop=None,
    ) -> None:
        """Послать последовательность.

        Пауза после каждого шага = его wait_after_ms, иначе общий gap_ms.
        should_stop() — колбэк прерывания: если вернёт True, маршрут
        обрывается между шагами (аналог аварийного стопа в follow.exe)."""
        for i, a in enumerate(actions):
            if should_stop and should_stop():
                return
            self.send(a)
            pause = a.wait_after_ms or (gap_ms if i < len(actions) - 1 else 0)
            if pause:
                # спим короткими отрезками, чтобы стоп срабатывал быстро
                slept = 0
                while slept < pause:
                    if should_stop and should_stop():
                        return
                    chunk = min(50, pause - slept)
                    time.sleep(chunk / 1000)
                    slept += chunk


class LogBackend(InputBackend):
    """Печатает действие вместо реального нажатия. Кросс-платформенный."""

    def send(self, action: InputAction) -> None:
        ts = time.strftime("%H:%M:%S")
        hold = f" (hold {action.hold_ms}ms)" if action.hold_ms else ""
        print(f"[{ts}] INPUT -> {action.key}{hold}")


class CallbackBackend(InputBackend):
    """Отдаёт каждое действие во внешний колбэк (для GUI/логов/тестов).
    Движок крутится в своём потоке, поэтому колбэк должен быть потокобезопасным
    (в GUI — складываем в очередь, читаем из main-потока)."""

    def __init__(self, on_input) -> None:
        self.on_input = on_input

    def send(self, action: InputAction) -> None:
        self.on_input(action)


class SendInputBackend(InputBackend):
    """Реальный ввод на Windows через user32.SendInput (ctypes).

    Для мышиных кликов (MOUSE_RIGHT, LEFTCLICK) нужен hwnd окна игры —
    передаётся опционально; без него клик идёт по текущей позиции курсора."""

    def __init__(self, hwnd: int | None = None) -> None:
        if not sys.platform.startswith("win"):
            raise RuntimeError(
                "SendInputBackend работает только на Windows. "
                "Используй LogBackend на других ОС."
            )
        from win_input import send_key, send_mouse_click, KEY_MAP
        self._send_key        = send_key
        self._send_mouse      = send_mouse_click
        self._key_map         = KEY_MAP
        self.hwnd             = hwnd   # опциональный handle окна игры

    def send(self, action: InputAction) -> None:
        from win_input import resolve_vk
        key = action.key.upper()

        # мышиные действия
        if key in ("MOUSE_RIGHT", "MOUSE_LEFT", "LEFTCLICK", "MOUSE_MIDDLE"):
            button = "right" if "RIGHT" in key else ("middle" if "MIDDLE" in key else "left")
            if self.hwnd:
                # клик в центр клиентской области окна
                import ctypes, ctypes.wintypes as wt
                r = wt.RECT()
                ctypes.windll.user32.GetClientRect(self.hwnd, ctypes.byref(r))
                cx = (r.right - r.left) // 2
                cy = (r.bottom - r.top) // 2
                pt = wt.POINT(cx, cy)
                ctypes.windll.user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
                self._send_mouse(pt.x, pt.y, button, action.hold_ms)
            else:
                import ctypes, ctypes.wintypes as wt
                pt = wt.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                self._send_mouse(pt.x, pt.y, button, action.hold_ms)
        else:
            self._send_key(key, action.hold_ms)
