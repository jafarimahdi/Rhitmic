# NinjaTrader Bridge — Setup & Management Guide

**Package:** NinjaTrader → CSV → Python robot
**Files:** `GoldBridgeExporter.cs` (NinjaTrader indicator) + `gold_robot_ntbridge.py` (your robot, v3)
**Goal:** stream live COMEX gold data into your Python robot through NinjaTrader's *authorized* Rithmic connection — no API permission needed.

```
   Rithmic servers
         │  (NinjaTrader's app is authorized — yours isn't)
         ▼
   NinjaTrader 8  ── GC chart with GoldBridgeExporter indicator
         │  (writes every trade / bid / ask / depth update)
         ▼
   C:\NinjaBridge\ticks.csv
         │  (the robot tails the file, like tail -f)
         ▼
   gold_robot_ntbridge.py  ──► your terminal:  [TRADE] [BID] [ASK] [BOOK] [ALERT]
```

---

## Part A — Install the indicator in NinjaTrader (one time, ~5 minutes)

1. **Download** `GoldBridgeExporter.cs` from the workspace and open it in Notepad — you'll need to paste its full content shortly.
2. In NinjaTrader's **Control Center** menu: **New → NinjaScript Editor**.
3. In the editor's left panel, right-click the **Indicators** folder → **New Indicator**.
4. Name it exactly: `GoldBridgeExporter` → click through the wizard with defaults → click **Generate** (a template with some code appears).
5. **Select ALL** the generated code (**Ctrl+A**), **delete** it, and **paste the entire content** of `GoldBridgeExporter.cs`.
6. Press **F5** to compile. The status bar (bottom of the editor) should say compilation succeeded with no errors. *(After compiling, NinjaTrader may add its own auto-generated code regions to the file — that's normal, leave them.)*
7. Close the editor.

> If you get compile errors, copy-paste the exact error text to me — I'll fix it. (I could not compile NinjaScript on my side.)

## Part B — Set up the Gold chart (one time, ~2 minutes)

1. Control Center: **New → Chart**.
2. In the instrument box type **GC** and select the **front-month contract with real volume** (e.g. `GC 09-26`). This is the contract your robot will watch. *(For Micro Gold use `MGC` instead.)*
3. Timeframe: anything, **1 Minute** is fine. 
4. On the chart: **right-click → Indicators…**
5. In the *Available* list (left side), find **GoldBridgeExporter**, double-click it (it moves to the right side).
6. On the right side you'll see its parameters:
   - **Output folder**: `C:\NinjaBridge` (default — change if you like)
   - **Export market depth (L2)**: `True` (default)
7. Click **OK**.
8. **Verify:** open File Explorer → `C:\NinjaBridge` → `ticks.csv` should exist. During market hours, open it in Notepad and watch new lines appear within seconds. (Extra check: Control Center → **New → Output** shows `GoldBridgeExporter: writing to C:\NinjaBridge\ticks.csv`.)

## Part C — Run the robot (~1 minute)

1. Download `gold_robot_ntbridge.py` from the workspace into your usual folder (e.g. `A:\gitHub\Rhitmic`).
2. In Git Bash:
   ```bash
   cd /a/gitHub/Rhitmic
   python gold_robot_ntbridge.py
   ```
3. You should see the banner, then — during market hours — a stream like:
   ```
   [TRADE ] GC 09-26 px=4,102.50 qty=3 @ 2026-09-07T14:32:01.123
   [BID   ] GC 09-26 4,102.25 x 12
   [ASK   ] GC 09-26 4,102.50 x 8
   [BOOK  ] GC 09-26 bids: 4,102.25x12  4,102.15x15  |  asks: 4,102.50x8  4,102.75x20
   [ALERT ] big trade   75 lots @ 4,102.50  (session volume 1,204)
   [STATS ] 41 events/s | total 12,345 | file 8.2 MB
   ```
4. **Ctrl+C** stops it.

**Robot options:**

| Command | What it does |
|---|---|
| `python gold_robot_ntbridge.py` | Live mode — only NEW events (default) |
| `python gold_robot_ntbridge.py --from-start` | Replays the whole file (good for first test / review) |
| `python gold_robot_ntbridge.py --only last` | Prints only trades (calmer terminal) |
| `python gold_robot_ntbridge.py --book-interval 0` | Turns off the [BOOK] summary |
| `python gold_robot_ntbridge.py --big 25` | Alert on single trades ≥ 25 lots |
| `python gold_robot_ntbridge.py --file D:\data\ticks.csv` | Use a different bridge file |

No `pip install` needed — the robot uses only the Python standard library.

> **Using a custom output folder?** The robot must be told where the file is:
> - either run it with the flag: `python gold_robot_ntbridge.py --file "A:/gitHub/Rhitmic/ticks.csv"` (forward slashes work best in Git Bash),
> - or make it the default: open `gold_robot_ntbridge.py` and change the line
>   `DEFAULT_FILE = os.environ.get("NT_BRIDGE_FILE", r"C:\NinjaBridge\ticks.csv")`
>   to end with `r"A:\gitHub\Rhitmic\ticks.csv"` instead — then plain `python gold_robot_ntbridge.py` works.
>
> If you forget, the robot just prints *Waiting for the bridge file* — nothing breaks.

---

## Daily operation & management

**Start order (each session):**
1. Open NinjaTrader → it auto-connects to Rithmic (check the connection status at the bottom of the Control Center is **green/connected**).
2. Make sure the **GC chart** (with the indicator) is open — a tab in the background is fine; **don't close the chart** while the robot runs. Minimizing the NinjaTrader window is OK.
3. Run `python gold_robot_ntbridge.py`.

**Stop order:** Ctrl+C in the robot terminal anytime; close NinjaTrader when done. NinjaTrader keeps writing to the file even when the robot is off, so you can restart the robot without touching NT.

**Market clock (Budapest time — your local time):**

| When | What happens |
|---|---|
| Mon–Fri 00:00–23:00 | Market open — data flows |
| **Daily 23:00–00:00** | CME Globex halt — no ticks (robot prints [STALE]) |
| 23:20–23:45 weekdays | Rithmic maintenance on top — data may pause |
| **Fri 23:00 → Mon 00:00** | Weekend — no ticks at all |

**When the robot prints [STALE]:** it's the checklist, in order of likelihood: (1) market closed (see table), (2) NinjaTrader disconnected, (3) the GC chart got closed. If NT reconnects after a drop, the file just continues — the robot resumes automatically.

**Data-file housekeeping:** `ticks.csv` grows a few MB per hour with depth on. Occasionally (e.g. weekly): stop the robot → delete `ticks.csv` → done — NinjaTrader automatically recreates it (with a fresh header) on the next tick. You cannot delete it while the robot is running (Windows locks open files).

**Trial expiry:** your Rithmic data inside NinjaTrader ends when the 14-day trial ends. Then: extend with Rithmic/a broker, or switch the robot's data source (Databento etc. — see `gold_data_alternatives.md`). The robot code stays the same; only the data source changes.

---

## Where your robot logic goes

Open `gold_robot_ntbridge.py` and find `on_event()` — every market event passes through it:

```python
def on_event(evt: dict, state: dict):
    # evt = {"time": ..., "event": "Last"/"Bid"/"Ask"/"DepthBid"/"DepthAsk",
    #        "price": ..., "size": ..., "instrument": "GC 09-26", ...}

    if evt["event"] == "Last":
        state["volume"] += evt["size"]
        if evt["size"] >= state["big_threshold"]:
            print(f"[ALERT ] big trade ...")     # <- included, working example
```

Ideas to build there: track best bid/ask and compute the spread; count trades per minute; simple moving average of last prices; volume-weighted average price. Everything your original Rithmic script wanted to do, you now do inside `on_event()`.

---

## Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| `ticks.csv` never created | Indicator not added to the chart; or folder permission denied → check the NT **Output** window for `GoldBridgeExporter: CANNOT create output file`, then set *Output folder* to e.g. `C:\Users\Jafar\NinjaBridge` in the indicator parameters |
| File created but no new lines | Market closed (see clock table); or NT disconnected (reconnect from Control Center); or you charted a dead/illiquid contract → use the front-month GC with volume |
| Robot says *Waiting for the bridge file* | NT/indicator not running yet, or wrong path → start NT first or pass `--file` |
| Robot prints nothing but no error | Same as "no new lines" — or run with `--from-start` to replay what's already in the file |
| Prices look like `4102,25` (comma) | You're running an older/modified indicator — re-install the current `GoldBridgeExporter.cs` (it forces dot decimals for Hungarian Windows) |
| `[STALE]` at 23:00 Budapest | Normal — daily halt/weekend |
| NinjaTrader feels slow in busy markets | In the indicator parameters, set **Export market depth (L2)** to `False` (depth is the high-volume part) |
| Robot crashed / weird lines in file | Restart it — malformed lines are skipped automatically and counted in [STATS] |

---

## Notes & limits (read once)

- Timestamps in the file are your **PC's local time** (that's what NinjaTrader reports for live events).
- NinjaTrader **must stay running** with the chart open while you use the robot.
- Level-2 depth comes through only if your NT/Rithmic feed provides DOM for GC — quick test: open a SuperDOM window for GC in NT; if it shows multiple price levels, depth works.
- The bridge is for **personal use** on your own trial data — don't redistribute the feed.
- If Rithmic later authorizes your API app (`gold_depth_reader_v2.py` ready and waiting), you can switch back to the direct connection — or keep both.
- Multiple charts with the indicator = multiple instruments in one file; the robot tracks a separate depth book per instrument automatically.
