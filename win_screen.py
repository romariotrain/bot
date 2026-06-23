"""
WIN_SCREEN — захват экрана через GDI/ctypes (Windows-only).

Drop-in замена macOS screencapture из screen.py.
Работает через BitBlt без внешних зависимостей.

WinScreenStateProvider — совместим с ScreenStateProvider по интерфейсу.
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass

gdi32    = ctypes.windll.gdi32
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# GDI constants
SRCCOPY        = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB         = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          wt.DWORD),
        ("biWidth",         ctypes.c_long),
        ("biHeight",        ctypes.c_long),
        ("biPlanes",        wt.WORD),
        ("biBitCount",      wt.WORD),
        ("biCompression",   wt.DWORD),
        ("biSizeImage",     wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed",       wt.DWORD),
        ("biClrImportant",  wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class WinScreenshot:
    """Захваченный прямоугольник экрана с пиксельным доступом."""

    def __init__(self, x: int, y: int, w: int, h: int, hwnd: int = 0) -> None:
        self.width  = w
        self.height = h
        self._pixels: list[int] = []
        self._capture(x, y, w, h, hwnd)

    def _capture(self, x: int, y: int, w: int, h: int, hwnd: int) -> None:
        hdc_src  = user32.GetDC(hwnd)
        hdc_mem  = gdi32.CreateCompatibleDC(hdc_src)
        hbmp     = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
        old_bmp  = gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_src, x, y, SRCCOPY)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize        = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth       = w
        bmi.bmiHeader.biHeight      = -h  # top-down
        bmi.bmiHeader.biPlanes      = 1
        bmi.bmiHeader.biBitCount    = 32
        bmi.bmiHeader.biCompression = BI_RGB

        buf = (ctypes.c_uint8 * (w * h * 4))()
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        # BGRA → store as flat list of 0xRRGGBB ints
        self._pixels = []
        for i in range(0, len(buf), 4):
            b, g, r = buf[i], buf[i+1], buf[i+2]
            self._pixels.append((r << 16) | (g << 8) | b)

        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_src)

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        idx = y * self.width + x
        v   = self._pixels[idx]
        return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF


def capture_region_win(x: int, y: int, w: int, h: int, hwnd: int = 0) -> WinScreenshot:
    """Захватить прямоугольник экрана. hwnd=0 — весь рабочий стол."""
    return WinScreenshot(x, y, w, h, hwnd)


# BarProbe and WinScreenStateProvider — reuse logic from screen.py

def color_dist(a: tuple[int,int,int], b: tuple[int,int,int]) -> float:
    return sum((p-q)**2 for p,q in zip(a,b)) ** 0.5


@dataclass
class BarProbe:
    """Probe заполненности полосы/шара вдоль линии (x1,y1)→(x2,y2)."""
    x1: int; y1: int; x2: int; y2: int
    fill_color: tuple[int,int,int]
    tol: float = 60.0
    samples: int = 20

    def measure(self, shot: WinScreenshot) -> float:
        hits = 0
        for i in range(self.samples):
            t = i / max(1, self.samples - 1)
            x = round(self.x1 + (self.x2 - self.x1) * t)
            y = round(self.y1 + (self.y2 - self.y1) * t)
            if 0 <= x < shot.width and 0 <= y < shot.height:
                if color_dist(shot.pixel(x, y), self.fill_color) <= self.tol:
                    hits += 1
        return hits / self.samples


class WinScreenStateProvider:
    """State-провайдер на основе GDI-захвата экрана (Windows-only).

    Совместим по интерфейсу с ScreenStateProvider из screen.py."""

    def __init__(
        self,
        region: tuple[int,int,int,int],
        probes: dict[str, BarProbe],
        hwnd: int = 0,
    ) -> None:
        from state import GameState
        self._GameState = GameState
        self.region = region
        self.probes = probes
        self.hwnd   = hwnd

    def read(self):
        x, y, w, h = self.region
        shot = capture_region_win(x, y, w, h, self.hwnd)
        vals = {name: probe.measure(shot) for name, probe in self.probes.items()}
        return self._GameState(
            hp=round(vals.get("hp", 1.0), 3),
            mana=round(vals.get("mana", 1.0), 3),
        )


if __name__ == "__main__":
    shot = capture_region_win(0, 0, 100, 100)
    print(f"Captured 100x100, top-left pixel: {shot.pixel(0,0)}")
