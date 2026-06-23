"""
WIN_WINDOW — работа с окном игры (Windows-only).

Нахождение HWND по PID, конвертация координат, управление фокусом.
Зеркалит использование GetWindowThreadProcessId / ClientToScreen из follow.exe.

Основные функции:
    find_hwnd(pid)                        — найти главное окно по PID
    get_client_rect(hwnd)                 — размер клиентской области
    client_to_screen(hwnd, x, y)          — клиентские → экранные координаты
    screen_to_client(hwnd, sx, sy)        — экранные → клиентские координаты
    set_foreground(hwnd)                  — вывести окно на передний план
    move_mouse_to_game(hwnd, gx, gy)      — переместить курсор в игровую точку
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ---------------------------------------------------------------- EnumWindows callback

_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def find_hwnd(pid: int, require_visible: bool = True) -> int:
    """Найти главное окно процесса по PID.

    Перебирает все окна верхнего уровня через EnumWindows и возвращает
    HWND первого видимого окна, принадлежащего указанному PID.

    Raises RuntimeError если окно не найдено."""
    result: list[int] = []

    def _cb(hwnd: int, _lparam: int) -> bool:
        if require_visible and not user32.IsWindowVisible(hwnd):
            return True
        pid_buf = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        if pid_buf.value == pid:
            result.append(hwnd)
            return False  # стоп — нашли
        return True

    user32.EnumWindows(_EnumWindowsProc(_cb), 0)

    if not result:
        raise RuntimeError(f"No window found for PID {pid}")
    return result[0]


def find_hwnd_wait(pid: int, timeout_s: float = 10.0, poll_ms: int = 100) -> int:
    """Ждать появления окна процесса до timeout_s секунд."""
    import time
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return find_hwnd(pid)
        except RuntimeError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Window for PID {pid} did not appear within {timeout_s}s")
        kernel32.Sleep(poll_ms)


# ---------------------------------------------------------------- геометрия

def get_client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Вернуть (left, top, right, bottom) клиентской области в экранных координатах."""
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    # GetClientRect даёт размеры относительно клиента — переводим в экранные
    pt = wt.POINT(r.left, r.top)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w = r.right - r.left
    h = r.bottom - r.top
    return pt.x, pt.y, pt.x + w, pt.y + h


def client_size(hwnd: int) -> tuple[int, int]:
    """Ширина и высота клиентской области."""
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Клиентские координаты окна → абсолютные экранные."""
    pt = wt.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def screen_to_client(hwnd: int, sx: int, sy: int) -> tuple[int, int]:
    """Абсолютные экранные координаты → клиентские координаты окна."""
    pt = wt.POINT(sx, sy)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


# ---------------------------------------------------------------- управление окном

def set_foreground(hwnd: int) -> None:
    """Вывести окно на передний план (SetForegroundWindow)."""
    user32.SetForegroundWindow(hwnd)


def get_window_pid(hwnd: int) -> int:
    """PID процесса-владельца окна."""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


# ---------------------------------------------------------------- мышь в игровых координатах

def move_mouse_to_game(hwnd: int, game_x: int, game_y: int) -> None:
    """Переместить курсор в точку игровых (клиентских) координат.

    game_x/game_y — пиксели внутри окна игры (клиентская система координат)."""
    sx, sy = client_to_screen(hwnd, game_x, game_y)
    from win_input import send_mouse_move
    send_mouse_move(sx, sy)


def click_in_game(
    hwnd: int,
    game_x: int,
    game_y: int,
    button: str = "left",
    hold_ms: int = 0,
) -> None:
    """Кликнуть по точке в клиентских координатах окна игры."""
    sx, sy = client_to_screen(hwnd, game_x, game_y)
    from win_input import send_mouse_click
    send_mouse_click(sx, sy, button, hold_ms)


# ---------------------------------------------------------------- самотест

if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if pid is None:
        # найти любое видимое окно на рабочем столе
        hwnds: list[int] = []
        def _cb(h, _): hwnds.append(h); return True
        user32.EnumWindows(_EnumWindowsProc(_cb), 0)
        hwnd = hwnds[0] if hwnds else None
        print(f"First visible HWND: {hwnd}")
    else:
        hwnd = find_hwnd(pid)
        x0, y0, x1, y1 = get_client_rect(hwnd)
        w, h = client_size(hwnd)
        print(f"HWND={hwnd}  screen=({x0},{y0})-({x1},{y1})  client={w}x{h}")
        cx, cy = client_to_screen(hwnd, w // 2, h // 2)
        print(f"Center in screen coords: ({cx}, {cy})")
