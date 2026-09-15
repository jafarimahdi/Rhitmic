"""
config.py
=========
STEP 0: Configuration, settings & constants for the gold trading system.

Loads values from a `.env` file (if present) and exposes them as module-level
constants. Every other step imports its settings from here.

`reload_env()` re-reads `.env` AND re-binds all constants, so editing `.env`
(credentials, market symbols, thresholds) takes effect in a running process
without a restart.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

for _d in (LOGS_DIR, DATA_DIR):
    _d.mkdir(exist_ok=True)


_DOTENV_KEYS = set()  # keys previously loaded from .env (for clean removal)


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency required).

    Values in `.env` OVERRIDE the environment. Keys that are REMOVED from the
    file are also removed from the environment on the next load, so editing
    `.env` down works correctly in a running process.
    """
    global _DOTENV_KEYS
    if not path.exists():
        for k in _DOTENV_KEYS:
            os.environ.pop(k, None)
        _DOTENV_KEYS = set()
        return

    # 1) collect the keys defined in the file
    file_keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        file_keys.add(line.split("=", 1)[0].strip())

    # 2) drop keys that were set from .env before but are no longer present
    for k in (_DOTENV_KEYS - file_keys):
        os.environ.pop(k, None)
    _DOTENV_KEYS = file_keys

    # 3) load values (python-dotenv if available, else manual parse)
    try:
        from dotenv import load_dotenv  # optional dependency
        load_dotenv(path, override=True)
        return
    except ImportError:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # strip an inline comment (a '#' preceded by whitespace)
        value = line.split("=", 1)[1]
        if "#" in value:
            cut = len(value)
            for i, ch in enumerate(value):
                if ch == "#" and i > 0 and value[i - 1] in (" ", "\t"):
                    cut = i
                    break
            value = value[:cut]
        key = line.split("=", 1)[0]
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _fget(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _fint(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _ffloat(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _refresh() -> None:
    """(Re)bind every module constant from the environment + .env."""
    g = globals()

    # ---- runtime / broker / symbol settings -------------------------------
    g["DEBUG"] = _fget("DEBUG", "0") == "1"
    g["BROKER_NAME"] = _fget("BROKER_NAME", "")
    g["MT5_TERMINAL_PATH"] = _fget("MT5_TERMINAL_PATH", "")
    g["SYMBOL"] = _fget("TRADING_SYMBOL", "XAUUSD")
    g["MT5_SYMBOL"] = _fget("MT5_SYMBOL", g["SYMBOL"])
    g["TIMEFRAME"] = _fget("TIMEFRAME", "M1")
    g["DATA_SOURCE"] = _fget("DATA_SOURCE", "demo")
    g["DATA_SYMBOL"] = _fget("DATA_SYMBOL") or _fget("RITHMIC_SYMBOL", "GC")
    g["DATA_MARKET"] = _fget("DATA_MARKET", "")
    g["TRADE_MARKET"] = _fget("TRADE_MARKET", "")

    # master on/off switch: 0 = analyse only, never send a trade signal
    g["TRADING_ENABLED"] = _fget("TRADING_ENABLED", "1") == "1"

    # execution routing: one and only one order owner
    #   none   = analysis only; clear/neutralise the EA signal
    #   python = Python MT5 SDK may send orders; EA receives neutral signal
    #   ea     = Python writes actionable signals; only the MQL5 EA trades
    mode = _fget("EXECUTION_MODE", "none").strip().lower()
    g["EXECUTION_MODE"] = mode if mode in ("none", "python", "ea") else "none"
    # Refuse to place orders on a REAL account unless explicitly allowed.
    # Demo/contest accounts are always fine. Keep 0 until going live is a
    # deliberate, reviewed decision.
    g["ALLOW_LIVE_TRADING"] = _fget("ALLOW_LIVE_TRADING", "0") == "1"

    # ---- STEP 2 analysis parameters ----------------------------------------
    g["PRICE_RESOLUTION"] = _ffloat("PRICE_RESOLUTION", 0.1)
    g["LARGE_ORDER_THRESHOLD"] = _ffloat("LARGE_ORDER_THRESHOLD", 100.0)
    g["CORRELATION_WINDOW"] = _fint("CORRELATION_WINDOW", 30)
    g["ECONOMIC_CALENDAR_TIMEOUT"] = _fint("ECONOMIC_CALENDAR_TIMEOUT", 8)

    # ---- multi-timeframe confirmation + spread guard (better results) -------
    g["CONFIRM_ENABLED"] = _fget("CONFIRM_ENABLED", "1") == "1"
    g["CONFIRM_TIMEFRAMES"] = _fget("CONFIRM_TIMEFRAMES", "H1,M15,M5")
    g["MAX_SPREAD_PCT"] = _ffloat("MAX_SPREAD_PCT", 0.05)  # block trades above this

    # ---- order blocks / supply-demand zones (smart-money levels) ------------
    g["ORDER_BLOCKS_ENABLED"] = _fget("ORDER_BLOCKS_ENABLED", "1") == "1"

    # ---- anti-overtrading guard (cooldown + daily cap) ----------------------
    g["COOLDOWN_MINUTES"] = _fint("COOLDOWN_MINUTES", 15)
    g["MAX_TRADES_PER_DAY"] = _fint("MAX_TRADES_PER_DAY", 20)

    # ---- STEP 3 / STEP 4 thresholds -----------------------------------------
    g["AI_CONFIDENCE_THRESHOLD"] = _ffloat("CONFIDENCE_THRESHOLD", 70.0)
    # Ask the AI when the Step-2 signal is at least this strong. This is only
    # a noise/quota saver — the REAL trade gate is the AI's own confidence
    # (>=70%), which is checked in Step 4.
    #    10 = ask the AI on any meaningful signal (it weighs in often)
    #    20 = ask only on clearly strong signals (AI asked much less often)
    # Lower number = Gemini gets consulted more often = more chances to trade.
    g["AI_MIN_SIGNAL_STRENGTH"] = _ffloat("AI_MIN_SIGNAL_STRENGTH", 10.0)
    # And never more often than this many minutes. Free Gemini gives ~1,500
    # requests/day and ~15/minute PER PROJECT per model; with 3 keys in 3
    # projects (~4,500/day), every 1 minute (~1,440/day) is only ~32%.
    g["AI_MIN_INTERVAL_MINUTES"] = _fint("AI_MIN_INTERVAL_MINUTES", 1)
    g["AI_MAX_CALLS_PER_DAY"] = _fint("AI_MAX_CALLS_PER_DAY", 2000)
    # How long a rate-limited key is skipped on later cycles. This is NOT a
    # wait between keys: failover to the next key is immediate.
    g["AI_KEY_COOLDOWN_MINUTES"] = _fint("AI_KEY_COOLDOWN_MINUTES", 20)
    # Maximum duration for one modern Gemini request, in milliseconds.
    # A failed request then moves to the next key/model immediately.
    g["GEMINI_REQUEST_TIMEOUT_MS"] = _fint("GEMINI_REQUEST_TIMEOUT_MS", 20000)
    # Seconds to verify that a broker-confirmed order becomes a live position.
    g["EXECUTION_VERIFY_SECONDS"] = _fint("EXECUTION_VERIFY_SECONDS", 5)
    g["RISK_PER_TRADE_PCT"] = _ffloat("RISK_PER_TRADE_PCT", 1.0)
    g["STOP_LOSS_ATR_MULT"] = _ffloat("STOP_LOSS_ATR_MULT", 1.5)
    g["TAKE_PROFIT_ATR_MULT"] = _ffloat("TAKE_PROFIT_ATR_MULT", 3.0)
    g["LOT_SIZE"] = _ffloat("LOT_SIZE", 0.1)

    # risk-based position sizing
    g["CONTRACT_SIZE"] = _ffloat("CONTRACT_SIZE", 100.0)
    g["ACCOUNT_EQUITY"] = _ffloat("ACCOUNT_EQUITY", 10000.0)
    g["MAX_LOT_SIZE"] = _ffloat("MAX_LOT_SIZE", 1.0)

    # ---- news-time behaviour ------------------------------------------------
    g["NEWS_WARNING_MINUTES"] = _ffloat("NEWS_WARNING_MINUTES", 30.0)
    g["NEWS_BLACKOUT_BEFORE_MINUTES"] = _ffloat("NEWS_BLACKOUT_BEFORE_MINUTES", 15.0)
    g["NEWS_BLACKOUT_AFTER_MINUTES"] = _ffloat("NEWS_BLACKOUT_AFTER_MINUTES", 30.0)
    g["NEWS_WIDEN_STOP_MULT"] = _ffloat("NEWS_WIDEN_STOP_MULT", 1.5)
    g["NEWS_REDUCE_SIZE_PCT"] = _ffloat("NEWS_REDUCE_SIZE_PCT", 0.5)

    # ---- v4 position manager (trade management while a position is open) ----
    # PM runs every loop cycle: it adopts the bot's open positions (magic
    # 234000 only), tightens far stops, moves to break-even, trails behind
    # structure and can close early on signal flips. Set PM_ENABLE=0 to get
    # the old open-and-forget behaviour back.
    g["PM_ENABLE"] = _fget("PM_ENABLE", "1") == "1"
    # move SL to break-even once profit reaches this multiple of initial risk
    g["PM_BE_TRIGGER_R"] = _ffloat("PM_BE_TRIGGER_R", 1.0)
    # trail the SL behind fresh demand/supply zones + POC (tighten only)
    g["PM_TRAIL_ENABLE"] = _fget("PM_TRAIL_ENABLE", "1") == "1"
    # close early when the composite signal flips this hard against us ...
    g["PM_FLIP_EXIT_SCORE"] = _ffloat("PM_FLIP_EXIT_SCORE", 55.0)
    # ... but only when order flow (delta/pressure) agrees (1) or not (0)
    g["PM_FLIP_REQUIRE_FLOW"] = _fget("PM_FLIP_REQUIRE_FLOW", "1") == "1"
    # close when CVD diverges against the position while it is still early
    g["PM_DIVERGENCE_EXIT"] = _fget("PM_DIVERGENCE_EXIT", "1") == "1"
    g["PM_DIVERGENCE_MIN_R"] = _ffloat("PM_DIVERGENCE_MIN_R", 0.3)
    # close positions older than N minutes that travelled < P of the TP leg
    g["PM_TIME_STOP_MINUTES"] = _fint("PM_TIME_STOP_MINUTES", 90)
    g["PM_TIME_STOP_MIN_PROGRESS"] = _ffloat("PM_TIME_STOP_MIN_PROGRESS", 0.2)
    # structural stop distances are clamped to [min, max] x ATR — this is
    # what stops the "SL too far" problem (old blind 1.5xATR stops)
    g["PM_MIN_SL_ATR"] = _ffloat("PM_MIN_SL_ATR", 1.2)
    g["PM_MAX_SL_ATR"] = _ffloat("PM_MAX_SL_ATR", 3.0)
    # buffer beyond a zone for the SL, and how far in front of opposing
    # structure the TP parks
    g["PM_ZONE_BUFFER_ATR"] = _ffloat("PM_ZONE_BUFFER_ATR", 0.25)
    g["PM_TP_BUFFER_ATR"] = _ffloat("PM_TP_BUFFER_ATR", 0.15)
    # keep this much clearance from strong round numbers (hunt protection)
    g["PM_ROUND_HUNT_BUFFER_ATR"] = _ffloat("PM_ROUND_HUNT_BUFFER_ATR", 0.12)
    # TP distance clamps in ATR multiples
    g["PM_TP_MIN_ATR"] = _ffloat("PM_TP_MIN_ATR", 1.0)
    g["PM_TP_MAX_ATR"] = _ffloat("PM_TP_MAX_ATR", 4.0)
    # minimum seconds between SL/TP modifications of the same position
    g["PM_MODIFY_COOLDOWN_SECONDS"] = _fint("PM_MODIFY_COOLDOWN_SECONDS", 180)

    # ---- v4.1 in-trade intelligence ----
    # H1/H4 Points of Control join the anchor pool ("POC in bigger candles")
    g["PM_HTF_POC_ENABLE"] = _fget("PM_HTF_POC_ENABLE", "1") == "1"
    # footprint stacked-imbalance clusters act as fresh zones: one side must
    # dominate by this ratio over N consecutive prices, with real volume
    g["PM_FP_ZONES_ENABLE"] = _fget("PM_FP_ZONES_ENABLE", "1") == "1"
    g["PM_FP_IMB_RATIO"] = _ffloat("PM_FP_IMB_RATIO", 3.0)
    g["PM_FP_MIN_RUN"] = _fint("PM_FP_MIN_RUN", 3)
    # flow health: if price moves in our favour but CVD disagrees, the
    # break-even trigger drops to this multiple of risk (protect early)
    g["PM_FLOW_ENABLE"] = _fget("PM_FLOW_ENABLE", "1") == "1"
    g["PM_FLOW_LOOKBACK_MINUTES"] = _fint("PM_FLOW_LOOKBACK_MINUTES", 5)
    g["PM_FLOW_WEAK_BE_R"] = _ffloat("PM_FLOW_WEAK_BE_R", 0.5)
    # VWAP regime: z-score that marks "trend side" (trail behind VWAP) and
    # "stretched" (lock half the gain); buffer for the VWAP trail stop
    g["PM_VWAP_ENABLE"] = _fget("PM_VWAP_ENABLE", "1") == "1"
    g["PM_VWAP_TREND_Z"] = _ffloat("PM_VWAP_TREND_Z", 0.5)
    g["PM_VWAP_STRETCH_Z"] = _ffloat("PM_VWAP_STRETCH_Z", 2.0)
    g["PM_VWAP_TRAIL_BUFFER_ATR"] = _ffloat("PM_VWAP_TRAIL_BUFFER_ATR", 0.25)

    # ---- v4.2 risk perimeter ----
    # news protection: when a HIGH-impact event (CPI/NFP/FOMC) is this many
    # minutes away: "tighten" locks gains on profitable positions (losers
    # keep their structural stop); "flatten" closes everything pre-release
    g["PM_NEWS_PROTECT_ENABLE"] = _fget("PM_NEWS_PROTECT_ENABLE", "1") == "1"
    g["PM_NEWS_PROTECT_MINUTES"] = _ffloat("PM_NEWS_PROTECT_MINUTES", 10.0)
    g["PM_NEWS_PROTECT_MODE"] = _fget("PM_NEWS_PROTECT_MODE", "tighten")
    # daily flatten: close ALL bot positions at this UTC time, BEFORE the
    # XAUUSD CFD break (~22:00 UTC) — a gap can jump straight over a stop.
    # This also covers the weekend (Friday). "" disables.
    g["PM_DAILY_FLATTEN_UTC"] = _fget("PM_DAILY_FLATTEN_UTC", "21:30")
    # never donate the spread: postpone SL/TP edits and non-urgent closes
    # while the CFD spread exceeds this percentage (news seconds)
    g["PM_ACTION_MAX_SPREAD_PCT"] = _ffloat("PM_ACTION_MAX_SPREAD_PCT", 0.05)

    # ---- v4.3 profit protection ----
    # profit ratchet: once the open gain reaches this many ATRs (in price
    # points), the SL never gives back more than PM_PROFIT_GIVEBACK of the
    # BEST gain seen — winners close as winners
    g["PM_PROFIT_LOCK_ENABLE"] = _fget("PM_PROFIT_LOCK_ENABLE", "1") == "1"
    g["PM_PROFIT_LOCK_MIN_ATR"] = _ffloat("PM_PROFIT_LOCK_MIN_ATR", 1.0)
    g["PM_PROFIT_GIVEBACK"] = _ffloat("PM_PROFIT_GIVEBACK", 0.5)
    # momentum exit: a PROFITABLE position (>= this R) closes at market
    # when flow health says "flow against the position" AND the composite
    # signal turns against it with at least this strength (softer than the
    # 55 flip exit — protecting profit deserves a faster trigger)
    g["PM_MOMENTUM_EXIT_ENABLE"] = _fget("PM_MOMENTUM_EXIT_ENABLE", "1") == "1"
    g["PM_MOMENTUM_MIN_R"] = _ffloat("PM_MOMENTUM_MIN_R", 0.3)
    g["PM_MOMENTUM_SIGNAL"] = _ffloat("PM_MOMENTUM_SIGNAL", 40.0)

    # ---- live news headlines (fed to the AI so it can weigh fundamentals) ----
    # FREE via Google News RSS — no key, no card needed. 0 disables it.
    g["NEWS_ENABLED"] = _fget("NEWS_ENABLED", "1") == "1"
    g["NEWS_CACHE_MINUTES"] = _fint("NEWS_CACHE_MINUTES", 15)   # re-fetch interval
    g["NEWS_MAX_HEADLINES"] = _fint("NEWS_MAX_HEADLINES", 20)   # headlines per cycle
    g["NEWS_TIMEOUT"] = _fint("NEWS_TIMEOUT", 8)                # per-request seconds

    # ---- live macro data (DXY / 10Y yield / VIX) fed to the AI --------------
    # FREE via Yahoo Finance — no key, no card needed. 0 disables it.
    g["MACRO_ENABLED"] = _fget("MACRO_ENABLED", "1") == "1"
    g["MACRO_CACHE_MINUTES"] = _fint("MACRO_CACHE_MINUTES", 15)  # re-fetch interval
    g["MACRO_TIMEOUT"] = _fint("MACRO_TIMEOUT", 8)               # per-request seconds

    # ---- STEP 5 -------------------------------------------------------------
    g["MONITOR_POLL_SECONDS"] = _fint("MONITOR_POLL_SECONDS", 60)

    # ---- trading session (weekend / market-closed protection) ---------------
    g["SESSION_ENFORCE"] = _fget("SESSION_ENFORCE", "1") == "1"
    g["TRADING_DAYS"] = _fget("TRADING_DAYS", "0,1,2,3,4")   # Mon=0 .. Sun=6
    g["DAILY_BREAK_START"] = _fget("DAILY_BREAK_START", "")  # "HH:MM" UTC, optional
    g["DAILY_BREAK_END"] = _fget("DAILY_BREAK_END", "")
    g["STALE_DATA_SECONDS"] = _fint("STALE_DATA_SECONDS", 300)  # no fresh data -> halt

    # ---- risk circuit-breaker ------------------------------------------------
    g["DAILY_LOSS_LIMIT_PCT"] = _ffloat("DAILY_LOSS_LIMIT_PCT", 3.0)  # % of equity
    g["MAX_DRAWDOWN_PCT"] = _ffloat("MAX_DRAWDOWN_PCT", 10.0)

    # ---- data recording / replay (useful for weekend testing) ----------------
    g["RECORD_DATA"] = _fget("RECORD_DATA", "0") == "1"
    g["REPLAY_FILE"] = _fget("REPLAY_FILE", "")  # path to a recorded market_data json

    # ---- automatic file maintenance (keeps the app light long-term) ----------
    g["MAINTENANCE_ENABLED"] = _fget("MAINTENANCE_ENABLED", "1") == "1"
    g["LOG_RETENTION_DAYS"] = _fint("LOG_RETENTION_DAYS", 7)        # keep 7 days of logs
    g["DECISIONS_LOG_MAX_ROWS"] = _fint("DECISIONS_LOG_MAX_ROWS", 5000)
    g["OUTCOMES_LOG_MAX_ROWS"] = _fint("OUTCOMES_LOG_MAX_ROWS", 2000)
    g["RECORD_RETENTION_DAYS"] = _fint("RECORD_RETENTION_DAYS", 30)  # keep recordings 30 days

    # ---- futures <-> CFD spread monitor --------------------------------------
    g["SPREAD_ALERT_PCT"] = _ffloat("SPREAD_ALERT_PCT", 2.0)  # warn beyond this basis

    # ---- API keys & credentials ---------------------------------------------
    g["DATABENTO_API_KEY"] = _fget("DATABENTO_API_KEY", "")
    g["RITHMIC_USERNAME"] = _fget("RITHMIC_USERNAME", "")
    g["RITHMIC_PASSWORD"] = _fget("RITHMIC_PASSWORD", "")
    g["GEMINI_API_KEY"] = _fget("GEMINI_API_KEY", "")
    g["GEMINI_MODEL"] = _fget("GEMINI_MODEL", "gemini-3.7-flash")
    # Fallback model list — Google retires models frequently, so the bot
    # automatically tries each model in order until one works. Current models
    # are listed newest-first; add/remove freely.
    g["GEMINI_MODELS"] = [m.strip() for m in _fget(
        "GEMINI_MODELS",
        "gemini-3.7-flash,gemini-3.5-flash,gemini-3.6-flash,gemini-2.5-flash"
    ).split(",") if m.strip()]
    # Optional EXTRA Gemini keys (different projects/accounts). The bot
    # rotates through them when one hits its daily quota. Same-project keys
    # share one quota, so use keys from DIFFERENT projects/accounts.
    g["GEMINI_API_KEYS"] = [k for k in (
        _fget("GEMINI_API_KEY", ""),
        _fget("GEMINI_API_KEY_2", ""),
        _fget("GEMINI_API_KEY_3", ""),
        _fget("GEMINI_API_KEY_4", ""),
        _fget("GEMINI_API_KEY_5", ""),
    ) if k]
    g["MT5_LOGIN"] = _fint("MT5_LOGIN", 0)
    g["MT5_PASSWORD"] = _fget("MT5_PASSWORD", "")
    g["MT5_SERVER"] = _fget("MT5_SERVER", "")

    # ---- Rithmic ------------------------------------------------------------
    g["RITHMIC_SYSTEM"] = _fget("RITHMIC_SYSTEM", "Rithmic Paper Trading")
    g["RITHMIC_APP_NAME"] = _fget("RITHMIC_APP_NAME", "GoldTradingBot")
    g["RITHMIC_APP_VERSION"] = _fget("RITHMIC_APP_VERSION", "1.0.0")
    g["RITHMIC_LIB"] = _fget("RITHMIC_LIB", "async_rithmic")
    g["RITHMIC_SYMBOL"] = _fget("RITHMIC_SYMBOL", "GC")
    g["RITHMIC_EXCHANGE"] = _fget("RITHMIC_EXCHANGE", "COMEX")
    # gateway url for async-rithmic (Chicago production gateway, used for
    # paper trading and live accounts)
    g["RITHMIC_URL"] = _fget("RITHMIC_URL", "rprotocol.rithmic.com:443")

    # ---- NinjaTrader bridge (DATA_SOURCE=ninjabridge) ----------------------
    # Live CME gold L1+L2 from the GoldBridgeExporter indicator's ticks.csv.
    g["NT_BRIDGE_FILE"] = _fget("NT_BRIDGE_FILE", "")      # empty = auto-detect
    g["NT_WINDOW_SECONDS"] = _fint("NT_WINDOW_SECONDS", 900)  # rolling tick window
    # How much of ticks.csv to re-read on startup (in MB). Bigger = deeper
    # candle/MTF history immediately after a restart. The file can be huge
    # after days of NT running; 64 MB ≈ several hours of events.
    g["NT_CATCHUP_MB"] = _fint("NT_CATCHUP_MB", 64)
    g["NT_WAIT_SECONDS"] = _fint("NT_WAIT_SECONDS", 5)        # first-data wait

    # ---- Databento ----------------------------------------------------------
    g["DATABENTO_DATASET"] = _fget("DATABENTO_DATASET", "GLBX.MDP3")
    g["DATABENTO_SCHEMA"] = _fget("DATABENTO_SCHEMA", "mbo")
    g["DATABENTO_SYMBOL"] = _fget("DATABENTO_SYMBOL", "GC.n.0")

    # ---- MT5 signal bridge --------------------------------------------------
    g["MT5_SIGNAL_FILE"] = _fget("MT5_SIGNAL_FILE", "")
    g["SIGNAL_MAX_AGE_SECONDS"] = _fint("SIGNAL_MAX_AGE_SECONDS", 180)


_load_dotenv(BASE_DIR / ".env")
_refresh()


def reload_env() -> None:
    """Re-read `.env` and re-bind all constants.

    Use this to pick up edited credentials / market symbols in a running
    process (the long-running `main.py --loop` calls it each cycle via the
    providers). The simplest workflow remains: edit `.env` -> restart.
    """
    _load_dotenv(BASE_DIR / ".env")
    _refresh()


def mt5_initialize(mt5_module) -> bool:
    """Initialize the selected MT5 terminal consistently across all modules.

    When several broker terminals are installed, `MT5_TERMINAL_PATH` pins the
    connection. Login/password/server are used only when `MT5_LOGIN` is nonzero;
    login=0 means use the already-running selected terminal.
    """
    kwargs = {}
    if MT5_TERMINAL_PATH:
        kwargs["path"] = MT5_TERMINAL_PATH
    if MT5_LOGIN:
        kwargs.update(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    return bool(mt5_module.initialize(**kwargs))


def credentials_configured() -> dict:
    """Return a {service: bool} map of which credentials are present."""
    return {
        "databento": bool(DATABENTO_API_KEY),
        "rithmic": bool(RITHMIC_USERNAME and RITHMIC_PASSWORD),
        "gemini": bool(GEMINI_API_KEY),
        # login=0 intentionally means use the already-running terminal.
        "mt5": bool((MT5_LOGIN == 0 and MT5_SYMBOL) or
                    (MT5_LOGIN and MT5_PASSWORD and MT5_SERVER)),

    }
