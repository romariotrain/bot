"""
TRADE — авто-принятие трейда от разрешённых игроков (аналог CTradeDialog из follow.exe).

TradeConfig задаёт whitelist игроков и клавишу принятия трейда.
on_trade_request(state, cfg) — предикат «есть входящий трейд от разрешённого игрока».

Использование в профиле:
  {
    "name": "auto trade",
    "trigger": {"type": "event", "field": "trade_request_from"},
    "behavior": "auto_trade",
    "params": {
      "allowed": ["MyLeader", "AltChar"],
      "accept_key": "ENTER",
      "decline_key": "ESCAPE"
    }
  }

state.trade_request_from выставляется StateProvider'ом когда
игровой движок получает запрос на трейд.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeConfig:
    """Настройки авто-трейда."""
    allowed: list[str] = field(default_factory=list)  # whitelist ников (case-insensitive)
    accept_key: str = "ENTER"    # клавиша подтверждения трейда
    decline_key: str = "ESCAPE"  # клавиша отклонения


def on_trade_request(state: "GameState", cfg: TradeConfig) -> bool:  # noqa: F821
    """True если есть входящий трейд от игрока из whitelist."""
    requester = state.trade_request_from.lower()
    if not requester:
        return False
    return not cfg.allowed or requester in {n.lower() for n in cfg.allowed}


def trade_config_from_dict(d: dict) -> TradeConfig:
    return TradeConfig(
        allowed     = d.get("allowed", []),
        accept_key  = d.get("accept_key", "ENTER"),
        decline_key = d.get("decline_key", "ESCAPE"),
    )
