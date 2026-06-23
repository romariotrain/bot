"""
WIN_XINPUT — XInput геймпад как дополнительный backend ввода (Windows-only).

Зеркалит XINPUT1_4.DLL Ordinal_2 (XInputGetState) из follow.exe.
Поддерживает маппинг кнопок геймпада в строки профиля.

XInputBackend — дроп-ин замена SendInputBackend для контроллеров.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------- структуры XInput

XINPUT_GAMEPAD_DPAD_UP        = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN      = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT      = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT     = 0x0008
XINPUT_GAMEPAD_START          = 0x0010
XINPUT_GAMEPAD_BACK           = 0x0020  # SELECT
XINPUT_GAMEPAD_LEFT_THUMB     = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB    = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER  = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A              = 0x1000
XINPUT_GAMEPAD_B              = 0x2000
XINPUT_GAMEPAD_X              = 0x4000
XINPUT_GAMEPAD_Y              = 0x8000

# Маппинг строк профиля → битовые маски (из strings.txt follow.exe)
BUTTON_MAP: dict[str, int] = {
    "DUP":      XINPUT_GAMEPAD_DPAD_UP,
    "DDOWN":    XINPUT_GAMEPAD_DPAD_DOWN,
    "DLEFT":    XINPUT_GAMEPAD_DPAD_LEFT,
    "DRIGHT":   XINPUT_GAMEPAD_DPAD_RIGHT,
    "START":    XINPUT_GAMEPAD_START,
    "SELECT":   XINPUT_GAMEPAD_BACK,
    "LB":       XINPUT_GAMEPAD_LEFT_SHOULDER,
    "RB":       XINPUT_GAMEPAD_RIGHT_SHOULDER,
    "A":        XINPUT_GAMEPAD_A,
    "B":        XINPUT_GAMEPAD_B,
    "X":        XINPUT_GAMEPAD_X,
    "Y":        XINPUT_GAMEPAD_Y,
    "LTHUMB":   XINPUT_GAMEPAD_LEFT_THUMB,
    "RTHUMB":   XINPUT_GAMEPAD_RIGHT_THUMB,
}

# Аналоговые пороги
TRIGGER_THRESHOLD = 30    # 0-255
STICK_THRESHOLD   = 8000  # -32768..32767


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons",      wt.WORD),
        ("bLeftTrigger",  ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX",      ctypes.c_short),
        ("sThumbLY",      ctypes.c_short),
        ("sThumbRX",      ctypes.c_short),
        ("sThumbRY",      ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wt.DWORD),
        ("Gamepad",        XINPUT_GAMEPAD),
    ]


# ---------------------------------------------------------------- XInput API

try:
    _xinput = ctypes.windll.xinput1_4
except AttributeError:
    try:
        _xinput = ctypes.windll.xinput9_1_0
    except AttributeError:
        _xinput = None


def get_state(controller_idx: int = 0) -> XINPUT_STATE | None:
    """Прочитать состояние геймпада. None если контроллер не подключён."""
    if _xinput is None:
        return None
    state = XINPUT_STATE()
    ret = _xinput.XInputGetState(controller_idx, ctypes.byref(state))
    return state if ret == 0 else None


def is_connected(controller_idx: int = 0) -> bool:
    return get_state(controller_idx) is not None


def get_pressed_buttons(controller_idx: int = 0) -> set[str]:
    """Вернуть множество нажатых кнопок (строки как в BUTTON_MAP)."""
    state = get_state(controller_idx)
    if state is None:
        return set()
    buttons = state.Gamepad.wButtons
    pressed = {name for name, mask in BUTTON_MAP.items() if buttons & mask}
    # аналоговые триггеры
    if state.Gamepad.bLeftTrigger > TRIGGER_THRESHOLD:
        pressed.add("LTDOWN")
    if state.Gamepad.bRightTrigger > TRIGGER_THRESHOLD:
        pressed.add("RTDOWN")
    # стики как CTRLDOWN (нажатие левого стика вниз = CTRLDOWN из strings.txt)
    if state.Gamepad.sThumbLY < -STICK_THRESHOLD:
        pressed.add("LDOWN")
    return pressed


# ---------------------------------------------------------------- XInputBackend

from backends import InputBackend, InputAction


class XInputBackend(InputBackend):
    """Backend, читающий геймпад и транслирующий нажатия в игровой ввод.

    Режим работы отличается от SendInputBackend: вместо программной отправки
    нажатий, XInputBackend читает физическое состояние контроллера и
    вызывает on_button(name) при каждом новом нажатии.

    Для прямой отправки кнопок геймпада через профиль используй send()."""

    def __init__(
        self,
        controller_idx: int = 0,
        on_button: "Callable[[str], None] | None" = None,
    ) -> None:
        self.controller_idx = controller_idx
        self.on_button      = on_button
        self._prev_buttons: set[str] = set()
        self._poll_thread: threading.Thread | None = None
        self._stop         = threading.Event()

    def send(self, action: InputAction) -> None:
        """XInput не посылает синтетических нажатий — делегируем SendInput."""
        from win_input import send_key
        send_key(action.key, action.hold_ms)

    def start_polling(self, interval_ms: int = 50) -> None:
        """Запустить фоновый поток чтения геймпада."""
        self._stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, args=(interval_ms,), daemon=True
        )
        self._poll_thread.start()

    def stop_polling(self) -> None:
        self._stop.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)

    def _poll_loop(self, interval_ms: int) -> None:
        while not self._stop.is_set():
            cur = get_pressed_buttons(self.controller_idx)
            new_buttons = cur - self._prev_buttons
            if self.on_button:
                for btn in new_buttons:
                    self.on_button(btn)
            self._prev_buttons = cur
            self._stop.wait(interval_ms / 1000)


if __name__ == "__main__":
    print(f"XInput connected: {is_connected()}")
    state = get_state()
    if state:
        print(f"Buttons: {state.Gamepad.wButtons:#06x}")
        print(f"Pressed: {get_pressed_buttons()}")
    else:
        print("No controller connected.")
