"""
ninja_bridge_provider.py
========================
STEP 1 data provider: live CME gold (L1 trades/quotes + L2 order book depth)
from the NinjaTrader bridge.

Data flow:
    NinjaTrader 8 chart (MGC/GC) + GoldBridgeExporter indicator
        -> ticks.csv  (time,event,price,size,level,operation,instrument)
        -> THIS PROVIDER (one background tailer thread keeps a live
           price-keyed book + a rolling window of trades)
        -> Step 2 market_data schema (tick_data / bid_depth / ask_depth)

Setup (.env):
    DATA_SOURCE=ninjabridge
    NT_BRIDGE_FILE=A:\\gitHub\\Rhitmic\\ticks.csv     (or empty = auto-detect)
    DATA_SYMBOL=MGC 12-26     (root symbol is what matters: MGC or GC)

Notes:
  * The pipeline re-creates providers on every pass; a MODULE-LEVEL shared
    tailer keeps the book and rolling tick window alive between passes.
  * The books are keyed by PRICE (Rithmic/NT depth positions are unstable
    display slots - the lesson learned in the bridge robot).
  * Rotates/resets of ticks.csv (the exporter's size cap) are detected and
    handled: state is rebuilt from the fresh file.
  * Feed health fields (has_data / last_data_age_seconds) drive the existing
    safety gates in main.py: no fresh data -> the bot refuses to trade.
"""

from __future__ import annotations

import csv
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config
from data_providers import BaseProvider

logger = logging.getLogger(__name__)

_CATCHUP_BYTES = 10 * 1024 * 1024      # re-read at most the last 10 MB on start
_PRUNE_INTERVAL = 2.0                  # seconds between tick-window prunes
_MAX_BOOK_LEVELS = 20                  # snapshot keeps at most this many per side


def _parse_ts(raw: str) -> Optional[datetime]:
    """Parse the bridge's ISO timestamp ('2026-09-14T18:00:31.423', local
    time) into an aware datetime. Returns None when unparseable."""
    try:
        dt = datetime.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        try:
            dt = dt.astimezone()          # naive local -> aware local
        except (OSError, ValueError):
            dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_bridge_file() -> str:
    """Find ticks.csv: explicit setting -> env -> common locations.
    Cold start (file does not exist yet): wait next to THIS script, so the
    one-folder layout works without any configuration."""
    candidates: List[str] = []
    cfg = (getattr(config, "NT_BRIDGE_FILE", "") or "").strip()
    if cfg:
        candidates.append(cfg)
    env = os.environ.get("NT_BRIDGE_FILE", "")
    if env:
        candidates.append(env)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "ticks.csv"))
    candidates.append(os.path.join(os.path.dirname(here), "ticks.csv"))
    candidates.append(r"A:\gitHub\Rhitmic\ticks.csv")
    candidates.append(r"C:\NinjaBridge\ticks.csv")
    for cand in candidates:
        if cand and os.path.exists(cand):
            return cand
    if cfg or env:
        return cfg or env
    return os.path.join(here, "ticks.csv")


def _file_identity(path: str):
    """(device, inode) - changes when the file is replaced/rotated."""
    try:
        st = os.stat(path)
        return (st.st_dev, st.st_ino)
    except OSError:
        return (None, None)


class _InstrumentState:
    """Per-instrument live state (one chart per instrument in NinjaTrader)."""

    __slots__ = ("bids", "asks", "ticks", "best_bid", "best_ask", "last_dt")

    def __init__(self):
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.ticks: List[Dict[str, Any]] = []   # {price, volume, side, ts}
        self.best_bid: float = 0.0
        self.best_ask: float = 0.0
        self.last_dt: Optional[datetime] = None

    def reset(self) -> None:
        self.bids, self.asks = {}, {}
        self.ticks = []
        self.best_bid = self.best_ask = 0.0
        self.last_dt = None


class _BridgeTail:
    """Background thread that tails ticks.csv and maintains live state."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        self.instruments: Dict[str, _InstrumentState] = {}
        self.line_count = 0
        self.bad_lines = 0
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="nt-bridge-tail",
                                       daemon=True)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ #
    def _state_for(self, instrument: str) -> _InstrumentState:
        st = self.instruments.get(instrument)
        if st is None:
            st = _InstrumentState()
            self.instruments[instrument] = st
        return st

    def _handle_line(self, line: str) -> None:
        """Parse one CSV line and update instrument state."""
        try:
            parts = next(csv.reader([line.rstrip("\r\n")]))
        except (StopIteration, csv.Error):
            self.bad_lines += 1
            return
        if len(parts) != 7 or parts[0] == "time":
            self.bad_lines += 1
            return
        try:
            price = float(parts[2])
            size = float(parts[3] or 0)
        except ValueError:
            self.bad_lines += 1
            return
        event = parts[1]
        instrument = parts[6] or "?"
        dt = _parse_ts(parts[0])
        if dt is None:
            dt = datetime.now().astimezone()

        st = self._state_for(instrument)
        self.line_count += 1

        if event == "Last":
            # tick rule: at/above ask = aggressive buy, at/below bid = sell
            if st.best_ask and price >= st.best_ask:
                side = "BUY"
            elif st.best_bid and price <= st.best_bid:
                side = "SELL"
            elif st.ticks:
                side = st.ticks[-1]["side"]
            else:
                side = "BUY"
            st.ticks.append({"price": price, "volume": size, "side": side, "ts": dt})
            st.last_dt = dt
        elif event == "Bid":
            st.best_bid = price
            st.last_dt = dt
        elif event == "Ask":
            st.best_ask = price
            st.last_dt = dt
        elif event == "DepthBid":
            if parts[5] == "Remove" or size <= 0:
                st.bids.pop(price, None)
            else:
                st.bids[price] = size
            st.last_dt = dt
        elif event == "DepthAsk":
            if parts[5] == "Remove" or size <= 0:
                st.asks.pop(price, None)
            else:
                st.asks[price] = size
            st.last_dt = dt
        # unknown event types are ignored silently

    # ------------------------------------------------------------------ #
    def _prune_old_ticks(self, window: float) -> None:
        """Keep only trades newer than `window` seconds (by event time)."""
        cutoff = time.time() - window
        for st in self.instruments.values():
            if st.ticks:
                keep_from = 0
                for i, t in enumerate(st.ticks):
                    if t["ts"].timestamp() >= cutoff:
                        keep_from = i
                        break
                else:
                    keep_from = len(st.ticks)
                if keep_from:
                    del st.ticks[:keep_from]
                else:
                    # newest event is still old (market halt) - keep last 200
                    if len(st.ticks) > 200:
                        del st.ticks[:-200]

    # ------------------------------------------------------------------ #
    def _catch_up(self, f) -> None:
        """Read the tail of an existing file so the book starts warm."""
        try:
            size = os.path.getsize(self.path)
            if size > _CATCHUP_BYTES:
                f.seek(size - _CATCHUP_BYTES)
                f.readline()                     # discard the partial line
            for line in f:
                if line.endswith("\n"):
                    self._handle_line(line)
        except OSError as exc:
            logger.warning("NT bridge catch-up read failed: %s", exc)

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        logger.info("NT bridge tailer: watching %s", self.path)
        if not os.path.exists(self.path):
            logger.info("NT bridge tailer: waiting for the file to appear ...")
        while not os.path.exists(self.path) and not self._stop.is_set():
            time.sleep(1.0)
        if self._stop.is_set():
            return

        f = open(self.path, "r", encoding="utf-8", errors="replace")
        ident = _file_identity(self.path)
        with self.lock:
            self._catch_up(f)
        last_prune = time.time()

        while not self._stop.is_set():
            pos = f.tell()
            line = f.readline()
            if line.endswith("\n"):
                with self.lock:
                    self._handle_line(line)
                    now = time.time()
                    if now - last_prune >= _PRUNE_INTERVAL:
                        last_prune = now
                        self._prune_old_ticks(
                            max(60, int(getattr(config, "NT_WINDOW_SECONDS", 900))))
                continue

            if line:                            # partial line - rewind
                f.seek(pos)
                time.sleep(0.05)
                continue

            # idle: rotation / reset detection
            time.sleep(0.25)
            try:
                gone = not os.path.exists(self.path)
                replaced = (not gone) and (
                    _file_identity(self.path) != ident
                    or os.path.getsize(self.path) < f.tell())
                if gone or replaced:
                    logger.info("NT bridge tailer: file was reset/rotated - "
                                "rebuilding state from the fresh file")
                    f.close()
                    while not os.path.exists(self.path) and not self._stop.is_set():
                        time.sleep(1.0)
                    if self._stop.is_set():
                        return
                    f = open(self.path, "r", encoding="utf-8", errors="replace")
                    ident = _file_identity(self.path)
                    with self.lock:
                        for st in self.instruments.values():
                            st.reset()
                        self._catch_up(f)
            except OSError:
                pass


# ---------------------------------------------------------------------- #
# Module-level shared tailer: survives provider re-creation each pass
# ---------------------------------------------------------------------- #
_TAIL: Optional[_BridgeTail] = None
_TAIL_LOCK = threading.Lock()


def _get_tail() -> _BridgeTail:
    global _TAIL
    with _TAIL_LOCK:
        if _TAIL is None:
            _TAIL = _BridgeTail(_resolve_bridge_file())
            _TAIL.start()
        return _TAIL


def _choose_instrument(instruments: Dict[str, _InstrumentState]) -> str:
    """Pick the instrument to feed Step 2: the one matching DATA_SYMBOL's
    root (e.g. 'GC' matches 'GC 12-26'), else the busiest one seen."""
    desired = (getattr(config, "DATA_SYMBOL", "") or "").strip()
    if desired:
        root = desired.split()[0].upper()
        for name, st in instruments.items():
            if name.split()[0].upper() == root and (st.ticks or st.bids or st.asks):
                return name
    best_name, best_score = "", -1
    for name, st in instruments.items():
        score = len(st.ticks) + len(st.bids) + len(st.asks)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


class NinjaBridgeProvider(BaseProvider):
    """Step-1 provider that reads the NinjaTrader bridge file."""

    name = "ninjabridge"

    def __init__(self):
        super().__init__()
        self.tail = _get_tail()

    # ------------------------------------------------------------------ #
    def acquire(self, symbol: str = "", **kwargs) -> Dict[str, Any]:
        # give the tailer a moment to see data (first call / NT just started)
        waited = 0.0
        wait_max = float(getattr(config, "NT_WAIT_SECONDS", 5))
        while waited < wait_max:
            with self.tail.lock:
                has = any(st.ticks or st.bids or st.asks
                          for st in self.tail.instruments.values())
            if has:
                break
            time.sleep(0.25)
            waited += 0.25

        with self.tail.lock:
            name = _choose_instrument(self.tail.instruments)
            st = self.tail.instruments.get(name)
            if st is not None:
                self.tick_data = [{"price": t["price"], "volume": t["volume"],
                                   "side": t["side"]} for t in st.ticks]
                self._trades = [{"timestamp": t["ts"].isoformat(),
                                 "price": t["price"],
                                 "volume": t["volume"]} for t in st.ticks]
                # defensive book cleanup: drop levels that are clearly stale
                # (asks below the best bid / bids above the best ask), but
                # never let a filter empty a whole side. Real NT feeds keep
                # the book consistent via Remove events - this is insurance.
                raw_bids = dict(st.bids)
                raw_asks = dict(st.asks)
                if st.best_ask:
                    kept = {p: s for p, s in raw_bids.items() if p <= st.best_ask}
                    if kept:
                        raw_bids = kept
                if st.best_bid:
                    kept = {p: s for p, s in raw_asks.items() if p >= st.best_bid}
                    if kept:
                        raw_asks = kept
                raw_bids = dict(sorted(raw_bids.items(), key=lambda kv: -kv[0])
                                [:_MAX_BOOK_LEVELS])
                raw_asks = dict(sorted(raw_asks.items(), key=lambda kv: kv[0])
                                [:_MAX_BOOK_LEVELS])
                self.bid_depth = raw_bids
                self.ask_depth = raw_asks
                self.order_book = {
                    "bids": [(p, s) for p, s in sorted(raw_bids.items(), reverse=True)],
                    "asks": [(p, s) for p, s in sorted(raw_asks.items())],
                }
                if st.last_dt is not None:
                    self._touch(st.last_dt)
            else:
                name = symbol or getattr(config, "DATA_SYMBOL", "GC")

        symbol_out = name or symbol or getattr(config, "DATA_SYMBOL", "GC")
        data = self.build_market_data(symbol=symbol_out)
        logger.info("NinjaBridge provider: %d ticks, %d bid levels, %d ask "
                    "levels for %s (file lines seen: %d)",
                    len(data.get("tick_data", [])),
                    len(data.get("bid_depth", {})),
                    len(data.get("ask_depth", {})),
                    symbol_out, self.tail.line_count)
        return data
