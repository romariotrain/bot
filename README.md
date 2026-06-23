# input rule-engine (учебный аналог follow.exe)

Generic движок автоматизации ввода: правила `{триггер → действие}`, тайминги,
humanize, профили. Построен как чистый референс архитектуры follow.exe —
без привязки к чужой онлайн-игре. Подходит для своей игры, автотестов,
accessibility, одиночных игр.

## Запуск

```bash
python3 main.py                     # правила из кода
python3 main.py profiles/demo.json  # правила из JSON-профиля
```

Зависимостей нет (только стандартная библиотека). Аварийный стоп — Ctrl+C.
По умолчанию активен `LogBackend` — он печатает «что нажал бы», поэтому
демо запускается на любой ОС, включая macOS.

## Файлы

| Файл | Роль | Аналог в follow.exe |
|------|------|---------------------|
| `backends.py` | слой ВВОДА (`InputBackend.send`) | ViGEmBus / Interception / SendInput |
| `state.py` | состояние игры (`GameState`) | у бота его НЕТ — он угадывает по пикселям |
| `engine.py` | rule-engine: триггеры + цикл | таймерный движок на `SetTimer`/потоках |
| `profiles.py` | загрузка правил из JSON | `Profiles\*.txt` (INI) |
| `main.py` | сборка и демо-запуск | `CFollowAppDlg` |

## Соответствие концепций

| follow.exe | здесь |
|------------|-------|
| `[INPUT=TIMED] Elapse=4000-4300` | `TimedTrigger(4000, 4300)` |
| health/mana/monster триггеры (по пикселям) | `StateTrigger(lambda s: s.hp < 0.35)` — по честному state |
| `[INPUT=NEWZONE]` | `EventTrigger(lambda s: s.zone)` |
| `Humanize=1` | `humanize_ms` + рандом интервала в `TimedTrigger` |
| `Cooldown=`, `Delay=` | `cooldown_ms`, `gap_ms` |
| `GetAsyncKeyState(0x23)` (End = стоп) | Ctrl+C / Stop (прерывает и маршрут) |
| `NavSlot1..6`, `NavPortal` (маршрут в `CreateThread`) | `async_run` правило с `wait_after_ms` по шагам |
| `MapQuant/MapRarity` реролл валюты | `reroll: {until, max_attempts}` |
| правило от нескольких условий | `all`/`any` в триггере (AND/OR) |
| FollowBot (HostDist/Forward/Right) | `behavior: follow` (движение к лидеру) |
| CAttackTab (hold ПКМ) | `behavior: attack` |
| CTargetDialog / Aim | `behavior: aim` |
| AutoLoot / LootDist | `behavior: loot` |
| COnRespawnTab (ре-аур) | `behavior: reactivate_auras` |
| AcceptParty / AcceptTrade | state-правило на `party_invite_from`/`trade_request_from` |
| CLeagueMechanics (allow) | условие `op: in` со списком механик |
| NavAltarAllow/Deny | условие `op: in` / `not_in` |
| UltBlacklist | условие `op: not_in` |
| KeepAlive (анти-AFK) | timed-правило |

## Профили в комплекте

| Профиль | Что показывает |
|---------|----------------|
| `profiles/demo.json` | timed-скилл, лайф/мана-фласк, combo на смену зоны |
| `profiles/autobot.json` | навигационный маршрут в потоке + фласка параллельно |
| `profiles/maproll.json` | реролл карты до составного критерия (quant И rarity) |
| `profiles/followbot.json` | все поведения FollowBot+AutoBot: follow, attack, aim, loot, фласка, keep-alive, accept party/trade, league/altar allow-листы, ultimatum blacklist, ре-ауры на респе |

## Ключевое отличие от бота

follow.exe «слеп»: он снаружи игры, поэтому ищет чужой процесс, берёт handle
через SeDebugPrivilege и читает HP **по цвету пикселя на экране**. Здесь
state читается **напрямую** (`GameState`) — точно, мгновенно, без захвата
экрана. В реальном проекте `StateProvider.read()` подменяется на чтение из
твоего движка.

## Чтение состояния с экрана (механизм CHealthTriggerTab)

Опционально state можно брать не из движка/симулятора, а **с твоего экрана** —
ровно как «слепой» follow.exe определяет HP по цвету шара. Только здесь это
твой собственный экран (легально, как любой скриншот-тул).

- `screen.py` — захват региона (`screencapture`) + чтение пикселей
  (`Tkinter.PhotoImage`, без сторонних зависимостей) + `BarProbe`
  (доля заполненности шара = «процент HP»).
- `calibrate.py` — найти координаты и цвет шара (аналог `CPositionHelperDlg`):
  ```bash
  python3 calibrate.py region 40 1300 200 40   # снять регион, посмотреть углы
  python3 calibrate.py hline 40 1320 200       # цвета вдоль линии HP-шара
  python3 calibrate.py point 60 1320           # цвет одного пикселя
  ```
- `screen_demo.py` — движок с `ScreenStateProvider`: правило «фласка при hp<35%»
  срабатывает по реальному экрану. Подставь свои `REGION`/`HP_PROBE` из калибровки.

Нюансы macOS:
- нужно разрешение **System Settings → Privacy & Security → Screen Recording**;
- на Retina картинка в 2× пикселях (регион 200×40 точек → 400×80 px), поэтому
  координаты `BarProbe` задавай в **пикселях картинки**, как показывает калибровка.

> В своей игре это не нужно (есть честный `GameState`) — модуль здесь для того,
> чтобы понять и пощупать сам механизм чтения по пикселям.

## Что дальше (нереализованные фазы)

- **Windows-ввод (главное для рабочего инструмента)**: дописать `SendInputBackend`
  (ctypes → user32.SendInput) и `GamepadBackend` (vgamepad → ViGEmBus). Сейчас
  активен `LogBackend` — он печатает действия, чтобы демо работало на любой ОС.
- **Точные таймеры на Windows**: `winmm.timeBeginPeriod(1)` для гранулярности 1мс.
- **Интеграция со своей игрой**: подменить `StateProvider.read()` на чтение
  состояния из движка вместо симулятора.
- **Упаковка в один .exe**: `pyinstaller --onefile gui.py` — даст standalone-файл
  без установленного Python (форма как у follow.exe).
