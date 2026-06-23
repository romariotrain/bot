"""
WIN_INPUT — реальный ввод клавиатуры и мыши через user32.SendInput (Windows-only).

Реализует то, что в follow.exe скрыто за обфусцированным слоем:
доставка нажатий клавиш и кликов мыши в активное окно.

Ключевые функции:
    send_key(vk_or_name, hold_ms=0)   — нажать и отпустить клавишу
    send_mouse_click(x, y, button)    — клик по абсолютным экранным координатам
    KEY_MAP                           — таблица строковых имён → VK-коды
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32

# ---------------------------------------------------------------- константы

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_SCANCODE    = 0x0008
KEYEVENTF_UNICODE     = 0x0004

MOUSEEVENTF_MOVE        = 0x0001
MOUSEEVENTF_LEFTDOWN    = 0x0002
MOUSEEVENTF_LEFTUP      = 0x0004
MOUSEEVENTF_RIGHTDOWN   = 0x0008
MOUSEEVENTF_RIGHTUP     = 0x0010
MOUSEEVENTF_MIDDLEDOWN  = 0x0020
MOUSEEVENTF_MIDDLEUP    = 0x0040
MOUSEEVENTF_ABSOLUTE    = 0x8000

INPUT_MOUSE    = 0
INPUT_KEYBOARD = 1

# ---------------------------------------------------------------- таблица клавиш
# Строки из профилей follow.exe → Windows Virtual Key Codes

KEY_MAP: dict[str, int] = {
    # Буквы
    **{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    # Цифры (верхний ряд)
    **{str(i): ord(str(i)) for i in range(10)},
    # Функциональные
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    # Навигация
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "HOME": 0x24, "END": 0x23,
    "INSERT": 0x2D, "DELETE": 0x2E,
    # Спец
    "SPACE": 0x20, "ENTER": 0x0D, "ESCAPE": 0x1B, "TAB": 0x09,
    "BACKSPACE": 0x08, "CAPSLOCK": 0x14, "PAUSE": 0x13,
    "PRINTSCRN": 0x2C, "SCROLLLOCK": 0x91, "NUMLOCK": 0x90,
    # Модификаторы
    "SHIFT": 0x10, "LSHIFT": 0xA0, "RSHIFT": 0xA1,
    "CONTROL": 0x11, "LCONTROL": 0xA2, "RCONTROL": 0xA3,
    "ALT": 0x12, "CANCEL": 0x03,
    # Numpad
    "NUMPAD0": 0x60, "NUMPAD1": 0x61, "NUMPAD2": 0x62,
    "NUMPAD3": 0x63, "NUMPAD4": 0x64, "NUMPAD5": 0x65,
    "NUMPAD6": 0x66, "NUMPAD7": 0x67, "NUMPAD8": 0x68,
    "NUMPAD9": 0x69, "NUMPADPERIOD": 0x6E, "SEPARATOR": 0x6C,
    # Пунктуация (US layout)
    "SEMICOLON": 0xBA, "EQUALS": 0xBB, "COMMA": 0xBC,
    "MINUS": 0xBD, "PERIOD": 0xBE, "SLASH": 0xBF,
    "TILDE": 0xC0, "LEFTBRACKET": 0xDB, "BACKSLASH": 0xDC,
    "RIGHTBRACKET": 0xDD, "SINGLEQUOTE": 0xDE,
    # Мышь (специальные имена)
    "MOUSE_LEFT": -1, "LEFTCLICK": -1,
    "MOUSE_RIGHT": -2,
    "MOUSE_MIDDLE": -3,
}


def resolve_vk(key: str) -> int:
    """Строку профиля → VK-код. Поддерживает hex ('0x52') и прямые int."""
    upper = key.upper()
    if upper in KEY_MAP:
        return KEY_MAP[upper]
    if upper.startswith("0X"):
        return int(upper, 16)
    try:
        return int(key)
    except ValueError:
        raise KeyError(f"Unknown key name: {key!r}")


# ---------------------------------------------------------------- структуры

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wt.WORD),
        ("wScan",       wt.WORD),
        ("dwFlags",     wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   wt.DWORD),
        ("dwFlags",     wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_    = [("type", wt.DWORD), ("_u", _INPUT_UNION)]


def _send(inputs: list[INPUT]) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


# ---------------------------------------------------------------- клавиатура

def _make_key_event(vk: int, key_up: bool) -> INPUT:
    inp = INPUT()
    inp.type      = INPUT_KEYBOARD
    inp.ki.wVk    = vk
    inp.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
    return inp


def send_key_down(vk: int) -> None:
    _send([_make_key_event(vk, False)])


def send_key_up(vk: int) -> None:
    _send([_make_key_event(vk, True)])


def send_key(key: str | int, hold_ms: int = 0) -> None:
    """Нажать (и отпустить) клавишу. hold_ms > 0 — удерживать N мс."""
    vk = resolve_vk(str(key)) if isinstance(key, str) else key
    if vk < 0:
        # мышь — обрабатывается отдельно
        _mouse_click_center(vk)
        return
    send_key_down(vk)
    if hold_ms > 0:
        time.sleep(hold_ms / 1000)
    send_key_up(vk)


# ---------------------------------------------------------------- мышь

def _screen_to_absolute(x: int, y: int) -> tuple[int, int]:
    """Перевести пиксельные координаты в абсолютные (0..65535) для MOUSEEVENTF_ABSOLUTE."""
    sw = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return (x * 65535) // sw, (y * 65535) // sh


def _mouse_click_center(sentinel: int) -> None:
    """Клик в текущей позиции курсора (используется когда координаты неизвестны)."""
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    button = {-1: "left", -2: "right", -3: "middle"}.get(sentinel, "left")
    send_mouse_click(pt.x, pt.y, button)


def send_mouse_move(x: int, y: int) -> None:
    ax, ay = _screen_to_absolute(x, y)
    inp = INPUT()
    inp.type       = INPUT_MOUSE
    inp.mi.dx      = ax
    inp.mi.dy      = ay
    inp.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    _send([inp])


def send_mouse_click(x: int, y: int, button: str = "left", hold_ms: int = 0) -> None:
    """Кликнуть по абсолютным экранным координатам."""
    ax, ay = _screen_to_absolute(x, y)

    down_flag, up_flag = {
        "left":   (MOUSEEVENTF_LEFTDOWN,   MOUSEEVENTF_LEFTUP),
        "right":  (MOUSEEVENTF_RIGHTDOWN,  MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }[button]

    def _make_mouse(flags: int) -> INPUT:
        inp = INPUT()
        inp.type       = INPUT_MOUSE
        inp.mi.dx      = ax
        inp.mi.dy      = ay
        inp.mi.dwFlags = flags | MOUSEEVENTF_ABSOLUTE
        return inp

    _send([_make_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)])
    _send([_make_mouse(down_flag)])
    if hold_ms > 0:
        time.sleep(hold_ms / 1000)
    _send([_make_mouse(up_flag)])


def send_right_click_hold(x: int, y: int, hold_ms: int) -> None:
    """Зажать правую кнопку на hold_ms мс (для непрерывных атак)."""
    send_mouse_click(x, y, "right", hold_ms)


# ---------------------------------------------------------------- самотест

if __name__ == "__main__":
    import sys
    print("KEY_MAP entries:", len(KEY_MAP))
    if "--test" in sys.argv:
        import time as _t
        print("Pressing F1 in 3 seconds...")
        _t.sleep(3)
        send_key("F1")
        print("Done.")
