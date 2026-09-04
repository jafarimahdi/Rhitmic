"""
Gold robot - NinjaTrader bridge edition (v3 of the gold data app)
================================================================

Reads the market data that the NinjaTrader indicator `GoldBridgeExporter`
writes to a CSV file and turns it into the same kind of live stream the
Rithmic version produced:

    [TRADE ] GC 09-26 px=4102.50 qty=3 @ 2026-09-07T14:32:01.123
    [BID   ] GC 09-26 4102.25 x 12
    [ASK   ] GC 09-26 4102.50 x 8
    [BOOK  ] bids: 4102.25x12 4102.20x8 | asks: 4102.50x8 4102.75x20
    [STATS ] 41 events/s | total 12,345 | file 8.2 MB

WHY THIS EXISTS: your Rithmic trial works inside NinjaTrader (NinjaTrader's
app is authorized by Rithmic), but custom apps are blocked by Rithmic's
permission policy. This bridge uses NinjaTrader's authorized connection as
the data source. No API permission needed.

PIPELINE:  Rithmic -> NinjaTrader (GC chart + GoldBridgeExporter)
           -> C:\\NinjaBridge\\ticks.csv  ->  THIS ROBOT

Requirements: Python 3.10+ only. No pip installs needed (stdlib only).

USAGE (Git Bash on your PC):
    python gold_robot_ntbridge.py                     # default file, new events only
    python gold_robot_ntbridge.py --from-start        # replay the whole file
    python gold_robot_ntbridge.py --only last         # print only trades
    python gold_robot_ntbridge.py --only last,bid,ask # no book summary lines
    python gold_robot_ntbridge.py --file D:\\data\\ticks.csv
    python gold_robot_ntbridge.py --big 25            # alert on trades >= 25 lots

MANAGEMENT:
    * Start order: 1) NinjaTrader (with the GC chart + indicator open),
      2) this robot. Stop order: Ctrl+C robot anytime; close NT when done.
    * [STALE] lines appear when no data arrives for 30 s - see the checklist
      it prints (market halt 23:00-00:00 Budapest daily, weekend Fri 23:00
      until Mon 00:00 Budapest, NT disconnected, or chart closed).
    * To reset the data file: STOP the robot first (Windows locks open files),
      then delete C:\\NinjaBridge\\ticks.csv - NinjaTrader recreates it.
    * Your robot logic goes in on_event() below - examples included.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

DEFAULT_FILE = os.environ.get("NT_BRIDGE_FILE", r"C:\NinjaBridge\ticks.csv")

# Gold market clock (Budapest time, your local time):
#   Daily halt : 23:00 - 00:00  (CME Globex maintenance)
#   Weekend    : Fri 23:00 -> Mon 00:00
#   Rithmic extra maintenance: 23:20 - 23:45 on weekdays (data may pause)


# ── Depth book ───────────────────────────────────────────────────────────────
class DepthBook:
    """Maintains the DOM ladder from level updates (position -> (price, size)).

    NinjaTrader depth operations:
      Add    = a new level is INSERTED at this position (deeper levels shift down)
      Update = the level at this position changes price/size
      Remove = the level at this position is deleted (deeper levels shift up)
    """

    def __init__(self):
        self.bids = {}   # position -> (price, size)
        self.asks = {}

    def apply(self, side: str, level: int, price: float, size: int, operation: str):
        book = self.bids if side == "Bid" else self.asks
        if operation == "Add":
            # shift deeper levels down one slot, then insert at the position
            pos = max(book.keys(), default=-1)
            while pos >= level:
                book[pos + 1] = book.pop(pos)
                pos -= 1
            book[level] = (price, size)
        elif operation == "Remove":
            # delete the position, shift deeper levels up one slot
            book.pop(level, None)
            pos = level + 1
            while pos in book:
                book[pos - 1] = book.pop(pos)
                pos += 1
        else:  # Update
            book[level] = (price, size)

    def top(self, n=5):
        # merge levels quoting the same price (sum their sizes), then sort
        def merged(book):
            out = {}
            for price, size in book.values():
                if size > 0:
                    out[price] = out.get(price, 0) + size
            return out
        bids = sorted(merged(self.bids).items(), key=lambda x: -x[0])[:n]
        asks = sorted(merged(self.asks).items(), key=lambda x: x[0])[:n]
        return bids, asks


# ── ROBOT LOGIC GOES HERE ────────────────────────────────────────────────────
# Every market event passes through on_event(). evt is a dict:
#   {"time": "2026-09-07T14:32:01.123", "event": "Last", "price": 4102.5,
#    "size": 3, "level": -1, "operation": "", "instrument": "GC 09-26"}
# event is one of: Last (trade), Bid, Ask, DepthBid, DepthAsk.
# Add your strategy below - two working examples are included.

def on_event(evt: dict, state: dict):
    # Example 1: alert on big trades ("block" prints)
    if evt["event"] == "Last":
        state["volume"] += evt["size"]
        if evt["size"] >= state["big_threshold"]:
            print(f"[ALERT ] big trade {evt['size']:>4} lots @ {evt['price']:,.2f}"
                  f"  (session volume {state['volume']:,})")

    # Example 2: track best bid/ask in state - uncomment to use:
    # if evt["event"] == "Bid":
    #     state["best_bid"] = (evt["price"], evt["size"])
    # if evt["event"] == "Ask":
    #     state["best_ask"] = (evt["price"], evt["size"])
    pass


# ── File tailing ─────────────────────────────────────────────────────────────
def wait_for_file(path: str):
    if os.path.exists(path):
        return
    print(f"Waiting for the bridge file: {path}")
    print("  (Start NinjaTrader with the GC chart + GoldBridgeExporter indicator,")
    print("   or pass another path with --file)")
    while not os.path.exists(path):
        time.sleep(1.0)
    print("File found - starting.\n")


def follow(path: str, from_start: bool):
    """Yields complete lines from the file as they appear (like tail -f).
    Yields None periodically when there is nothing new, so the main loop
    can run its housekeeping (book summaries, stats, staleness watchdog)."""
    wait_for_file(path)
    f = open(path, "r", encoding="utf-8", errors="replace")
    if not from_start:
        f.seek(0, os.SEEK_END)  # jump to end: only NEW events

    while True:
        pos = f.tell()
        line = f.readline()
        if line.endswith("\n"):
            yield line
        elif line:  # partial line at EOF - rewind and retry later
            f.seek(pos)
            yield None
            time.sleep(0.1)
        else:  # nothing new - yield a housekeeping tick
            time.sleep(0.25)
            try:
                if os.path.getsize(path) < f.tell():
                    print("[BRIDGE] data file was reset - continuing from the top")
                    f.seek(0)
            except OSError:
                pass
            yield None


def parse_line(line: str):
    parts = next(csv.reader([line.rstrip("\r\n")]))
    if len(parts) != 7 or parts[0] == "time":  # header or malformed
        return None
    try:
        return {
            "time": parts[0],
            "event": parts[1],
            "price": float(parts[2]),
            "size": int(float(parts[3] or 0)),
            "level": int(parts[4]) if parts[4] else -1,
            "operation": parts[5],
            "instrument": parts[6],
        }
    except ValueError:
        return None


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Gold robot - NinjaTrader bridge edition")
    ap.add_argument("--file", default=DEFAULT_FILE, help="path to ticks.csv from the NT indicator")
    ap.add_argument("--from-start", action="store_true", help="process the file from the beginning (replay)")
    ap.add_argument("--only", default="last,bid,ask", help="which L1 events to print: last,bid,ask")
    ap.add_argument("--book-interval", type=float, default=5.0, help="seconds between [BOOK] summaries (0 = off)")
    ap.add_argument("--stale-after", type=float, default=30.0, help="seconds of silence before [STALE] warning")
    ap.add_argument("--big", type=int, default=50, help="alert when a single trade is >= this many lots")
    args = ap.parse_args()

    show = {s.strip().lower() for s in args.only.split(",") if s.strip()}
    path = args.file

    print("=" * 74)
    print("GOLD ROBOT - NinjaTrader bridge edition")
    print("=" * 74)
    print(f"  data file : {path}")
    print(f"  mode      : {'replay whole file' if args.from_start else 'live (new events only)'}")
    print(f"  printing  : {', '.join(sorted(show)) or 'nothing'}"
          + (f" | book every {args.book_interval:.0f}s" if args.book_interval else ""))
    print("  stop      : Ctrl+C")
    print("=" * 74)
    print()
    print("Waiting for market data... (lines appear once NinjaTrader writes them)")
    print()

    books = {}          # instrument -> DepthBook
    state = {"volume": 0, "big_threshold": args.big, "best_bid": None, "best_ask": None}
    total = 0
    skipped = 0
    started = time.time()
    last_event_mono = time.monotonic()   # counts from startup: warns if nothing ever arrives
    last_book_at = 0.0
    last_stats_at = 0.0
    stale_reported_at = 0.0

    try:
        for item in follow(path, args.from_start):
            now = time.monotonic()

            if item is None:  # idle tick from follow() - housekeeping only
                evt = None
            else:
                evt = parse_line(item)
                if evt is None:
                    skipped += 1
                    continue

            if evt is not None:
                total += 1
                last_event_mono = now
                ev = evt["event"]

                # --- dispatch by event type ----------------------------------
                if ev == "Last" and "last" in show:
                    print(f"[TRADE ] {evt['instrument']} px={evt['price']:,.2f} "
                          f"qty={evt['size']} @ {evt['time']}")
                elif ev == "Bid" and "bid" in show:
                    print(f"[BID   ] {evt['instrument']} {evt['price']:,.2f} x {evt['size']}")
                elif ev == "Ask" and "ask" in show:
                    print(f"[ASK   ] {evt['instrument']} {evt['price']:,.2f} x {evt['size']}")
                elif ev in ("DepthBid", "DepthAsk"):
                    book = books.setdefault(evt["instrument"], DepthBook())
                    book.apply(ev[len("Depth"):], evt["level"], evt["price"], evt["size"],
                               evt["operation"])

                # --- your robot logic ------------------------------------------
                on_event(evt, state)

            # --- periodic book summary (also fires when the market goes quiet) ---
            if args.book_interval and now - last_book_at >= args.book_interval and books:
                last_book_at = now
                for inst, book in books.items():
                    bids, asks = book.top()
                    if not bids and not asks:
                        continue
                    b = "  ".join(f"{p:,.2f}x{s}" for p, s in bids)
                    a = "  ".join(f"{p:,.2f}x{s}" for p, s in asks)
                    print(f"[BOOK  ] {inst} bids: {b}  |  asks: {a}")

            # --- periodic stats ------------------------------------------------
            if last_stats_at and now - last_stats_at >= 60.0:
                last_stats_at = now
                try:
                    size_mb = os.path.getsize(path) / 1e6
                except OSError:
                    size_mb = 0.0
                rate = total / max(1e-9, now - started)
                print(f"[STATS ] {rate:,.0f} events/s | total {total:,} | skipped {skipped:,} "
                      f"| file {size_mb:,.1f} MB")
            elif not last_stats_at:
                last_stats_at = now

            # --- staleness watchdog ---------------------------------------------
            if (args.stale_after
                    and now - last_event_mono > args.stale_after
                    and now - stale_reported_at > 60.0):
                stale_reported_at = now
                print("[STALE ] no data for a while - checklist:")
                print("         1. Gold market clock (Budapest): daily halt 23:00-00:00,")
                print("            weekend Fri 23:00 -> Mon 00:00")
                print("         2. Is NinjaTrader running and connected (green status)?")
                print("         3. Is the GC chart with GoldBridgeExporter still open?")

    except KeyboardInterrupt:
        pass

    elapsed = time.time() - started
    print(f"\nStopped. Processed {total:,} events in {elapsed/60:.1f} min "
          f"({total/max(1e-9,elapsed):,.0f} events/s). Session volume: {state['volume']:,} lots.")
    if skipped:
        print(f"({skipped:,} malformed/header lines were skipped - normal.)")


if __name__ == "__main__":
    main()
