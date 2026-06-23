"""
КАЛИБРОВКА — аналог CPositionHelperDlg из follow.exe.

Помогает найти, ГДЕ на экране твой индикатор (HP-шар и т.п.) и какого он
цвета, чтобы потом задать BarProbe. follow.exe заставляет это делать руками
по той же причине — у всех своё разрешение и UI.

Использование:
  python3 calibrate.py point X Y                     # цвет одного пикселя
  python3 calibrate.py hline X Y W                    # цвета вдоль горизонтали
  python3 calibrate.py region X Y W H                 # сохранить регион в PNG

Требует разрешения macOS на запись экрана (Screen Recording).
"""

from __future__ import annotations

import sys
import tkinter as tk

from screen import Screenshot, capture_region


def _shot(x, y, w, h):
    root = tk.Tk(); root.withdraw()
    png = capture_region(x, y, w, h)
    return Screenshot(png, root), root, png


def cmd_point(x, y):
    shot, root, png = _shot(x, y, 1, 1)
    print(f"({x},{y}) -> RGB {shot.pixel(0, 0)}")
    root.destroy()


def cmd_hline(x, y, w):
    shot, root, png = _shot(x, y, w, 1)
    print(f"Горизонталь от ({x},{y}) длиной {w}px:")
    for i in range(0, w, max(1, w // 20)):
        print(f"  +{i:4d}: RGB {shot.pixel(i, 0)}")
    root.destroy()


def cmd_region(x, y, w, h):
    shot, root, png = _shot(x, y, w, h)
    print(f"Сохранён регион {w}x{h} из ({x},{y}) -> {png}")
    print(f"Углы: TL={shot.pixel(0,0)}  TR={shot.pixel(w-1,0)}  "
          f"BL={shot.pixel(0,h-1)}  BR={shot.pixel(w-1,h-1)}")
    root.destroy()


def main():
    a = sys.argv
    if len(a) >= 4 and a[1] == "point":
        cmd_point(int(a[2]), int(a[3]))
    elif len(a) >= 5 and a[1] == "hline":
        cmd_hline(int(a[2]), int(a[3]), int(a[4]))
    elif len(a) >= 6 and a[1] == "region":
        cmd_region(int(a[2]), int(a[3]), int(a[4]), int(a[5]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
