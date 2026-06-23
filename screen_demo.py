"""
ДЕМО: движок реагирует на HP, прочитанный с ТВОЕГО экрана (механизм follow.exe).

Вместо симулятора стейта подключаем ScreenStateProvider: он каждый тик
снимает регион экрана и измеряет заполненность HP-шара. Правило «фласка при
hp<35%» срабатывает по реальной картинке.

Перед запуском откалибруй координаты шара через calibrate.py и подставь их
ниже (REGION + HP_PROBE). По умолчанию стоят примерные значения для левого
нижнего угла — почти наверняка их нужно поправить под свой экран/игру.

Запуск:  python3 screen_demo.py
Стоп:    Ctrl+C
Нужно разрешение macOS на запись экрана.
"""

from __future__ import annotations

import time

from backends import InputAction, LogBackend
from engine import Engine, Rule, StateTrigger
from screen import BarProbe, ScreenStateProvider

# --- ПОДСТАВЬ СВОИ КООРДИНАТЫ (из calibrate.py) ---
REGION = (40, 1300, 200, 40)        # bbox региона экрана: x, y, w, h
HP_PROBE = BarProbe(                 # линия вдоль HP-шара ОТНОСИТЕЛЬНО региона
    x1=0, y1=20, x2=199, y2=20,
    fill_color=(200, 30, 30),        # цвет «полного» HP (красный) — уточни калибровкой
    tol=70, samples=20,
)


def main():
    provider = ScreenStateProvider(REGION, {"hp": HP_PROBE})
    rules = [
        Rule(
            name="life-flask @ hp<35% (screen-read)",
            trigger=StateTrigger(lambda s: s.hp < 0.35, edge=True),
            actions=[InputAction("1")],
            cooldown_ms=3000,
        ),
    ]
    engine = Engine(LogBackend(), provider, rules, tick_ms=300)  # ~3 кадра/сек
    engine.start()
    print("Читаю HP с экрана. Ctrl+C — стоп.\n")
    try:
        while True:
            s = provider.read()
            print(f"  screen hp = {s.hp:.2f}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] стоп")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
