"""
ЧТЕНИЕ СОСТОЯНИЯ С ЭКРАНА (macOS) — механизм CHealthTriggerTab из follow.exe,
но на ТВОЁМ собственном экране.

Идея ровно как у оригинала: state не из памяти, а с картинки. Захватываем
регион экрана, и по заполненности «шара» (доле пикселей нужного цвета вдоль
линии) определяем HP/ману. Калибровка координат — аналог CPositionHelperDlg.

Зависимостей нет: захват — системный `screencapture`, чтение пикселей —
Tkinter.PhotoImage (входит в стандартный Python).

Требуется разрешение macOS: System Settings → Privacy & Security →
Screen Recording → разрешить терминалу/Python (иначе скрин будет чёрным).
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass

import tkinter as tk


# ---------------------------------------------------------------- захват

def capture_region(x: int, y: int, w: int, h: int) -> str:
    """Снимок прямоугольника экрана в PNG, возвращает путь к файлу.
    -x = без звука затвора, -R = регион x,y,w,h (в точках)."""
    path = tempfile.mktemp(suffix=".png")
    subprocess.run(["screencapture", "-x", f"-R{x},{y},{w},{h}", path],
                   check=True)
    return path


class Screenshot:
    """Загруженный PNG с доступом к пикселям. Нужен живой Tk root."""

    def __init__(self, png_path: str, root: tk.Tk) -> None:
        self.img = tk.PhotoImage(file=png_path, master=root)
        self.width = self.img.width()
        self.height = self.img.height()

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        v = self.img.get(x, y)
        if isinstance(v, str):
            return tuple(int(n) for n in v.split())[:3]  # "r g b"
        return tuple(v)[:3]


# ---------------------------------------------------------------- цвет

def color_dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


def is_match(c: tuple[int, int, int], target: tuple[int, int, int], tol: float) -> bool:
    return color_dist(c, target) <= tol


# ---------------------------------------------------------------- проба-«шар»

@dataclass
class BarProbe:
    """Проба заполненности полоски/шара вдоль линии (x1,y1)->(x2,y2).

    fill_color — цвет «полного» (для HP красный, для маны синий).
    Возвращает долю 0..1 = сколько точек вдоль линии совпали с fill_color.
    Это и есть «процент HP» как его видит follow.exe."""
    x1: int
    y1: int
    x2: int
    y2: int
    fill_color: tuple[int, int, int]
    tol: float = 60.0
    samples: int = 20

    def measure(self, shot: Screenshot) -> float:
        hits = 0
        for i in range(self.samples):
            t = i / max(1, self.samples - 1)
            x = round(self.x1 + (self.x2 - self.x1) * t)
            y = round(self.y1 + (self.y2 - self.y1) * t)
            if 0 <= x < shot.width and 0 <= y < shot.height:
                if is_match(shot.pixel(x, y), self.fill_color, self.tol):
                    hits += 1
        return hits / self.samples


# ---------------------------------------------------------------- провайдер

class ScreenStateProvider:
    """State-провайдер, читающий экран вместо симулятора.

    probes: {"имя_поля_GameState": BarProbe}. Регион захвата — общий bbox,
    координаты проб задаются ОТНОСИТЕЛЬНО региона.
    Подключается в Engine так же, как StateProvider.
    """

    def __init__(self, region: tuple[int, int, int, int], probes: dict[str, BarProbe]) -> None:
        from state import GameState  # локальный импорт, чтобы избежать цикла
        self._GameState = GameState
        self.region = region
        self.probes = probes
        self._root = tk.Tk()
        self._root.withdraw()

    def read(self):
        x, y, w, h = self.region
        png = capture_region(x, y, w, h)
        shot = Screenshot(png, self._root)
        vals = {name: probe.measure(shot) for name, probe in self.probes.items()}
        # маппим измеренные доли в поля GameState (hp/mana — это доли 0..1)
        return self._GameState(
            hp=round(vals.get("hp", 1.0), 3),
            mana=round(vals.get("mana", 1.0), 3),
        )
