"""
KEEPALIVE — мониторинг процесса игры и перезапуск движка при краше (Windows-only).

Зеркалит механизм из follow.exe: фоновый поток периодически вызывает
GetExitCodeProcess; если процесс завершился (код != STILL_ACTIVE=259),
движок останавливается и опционально вызывается restart_fn.

Использование:
    handle, pid = launch_as_user(...)       # или attach_game()
    ka = KeepAlive(handle, engine,
                   on_crash=lambda: launch_as_user(...))
    ka.start()
    ...
    ka.stop()
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time
from typing import Callable

kernel32 = ctypes.windll.kernel32

STILL_ACTIVE = 259  # GetExitCodeProcess возвращает это пока процесс жив


class KeepAlive:
    """Фоновый поток мониторинга процесса игры.

    Каждые poll_ms мс проверяет GetExitCodeProcess(handle).
    При краше:
      1. Вызывает engine.stop()
      2. Вызывает on_crash(), если задан (для перезапуска игры/движка)

    Поток автоматически завершается после обнаружения краша (однократно).
    Для постоянного наблюдения on_crash должен переподключить новый handle
    и вызвать ka.restart(new_handle)."""

    def __init__(
        self,
        handle: wt.HANDLE,
        engine,                          # engine.Engine — stop() вызывается при краше
        on_crash: Callable[[], None] | None = None,
        poll_ms: int = 1000,
    ) -> None:
        self.handle   = handle
        self.engine   = engine
        self.on_crash = on_crash
        self.poll_ms  = poll_ms

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Запустить мониторинг."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="keepalive")
        self._thread.start()

    def stop(self) -> None:
        """Остановить мониторинг (без остановки движка)."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def restart(self, new_handle: wt.HANDLE) -> None:
        """Заменить отслеживаемый handle и перезапустить мониторинг.

        Вызывать из on_crash после того, как игра перезапущена."""
        self.stop()
        self.handle = new_handle
        self.start()

    def _is_alive(self) -> bool:
        code = wt.DWORD()
        ok = kernel32.GetExitCodeProcess(self.handle, ctypes.byref(code))
        if not ok:
            return False
        return code.value == STILL_ACTIVE

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._is_alive():
                self._handle_crash()
                return
            self._stop_event.wait(self.poll_ms / 1000)

    def _handle_crash(self) -> None:
        print("[keepalive] game process exited — stopping engine")
        try:
            self.engine.stop()
        except Exception as e:
            print(f"[keepalive] engine.stop() error: {e}")

        if self.on_crash:
            try:
                self.on_crash()
            except Exception as e:
                print(f"[keepalive] on_crash() error: {e}")


if __name__ == "__main__":
    import sys
    print("KeepAlive module — import and use KeepAlive(handle, engine, on_crash=...).")
    print(f"STILL_ACTIVE = {STILL_ACTIVE}")
