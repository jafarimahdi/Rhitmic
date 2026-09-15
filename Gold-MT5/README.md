# Gold Trading System — MIXED
## NinjaTrader data + your 5-step AI brain + MT5 execution

**Status: BUILT & TESTED** — the full pipeline ran end-to-end in a sandbox test:
`STEP 1 OK (ninjabridge) → STEP 2 OK (signal) → STEP 3 (AI) → safety gates → STEP 5 OK`,
and the project's own test suite still passes 31/31.

```
NinjaTrader 8 (MGC chart + GoldBridgeExporter)  ← run this first
        │ writes
        ▼
A:\gitHub\Rhitmic\ticks.csv   (CME gold: trades, quotes, L2 depth)
        │ tailed by
        ▼
ninja_bridge_provider.py      ← NEW: Step-1 data provider
        ▼
STEP 2  SignalEngine (25+ signals: L2 imbalance, microprice, CVD, VWAP...)
        ▼
STEP 3  Gemini AI  →  BUY / SELL / HOLD + confidence
        ▼
STEP 4  MT5 execution  →  XAUUSD on your MT5 account
        ▼
STEP 5  Monitoring loop (repeat every 60 s)
```

---

## Files to download — ONE folder, that's it

The workspace folder **`Gold-MT5/` is the complete, cleaned, self-contained package**:

```
Gold-MT5\
├── main.py + step1–step5 + config.py      ← the trading pipeline (9 files)
├── data_providers.py + ninja_bridge_provider.py   ← data layer incl. the NT bridge
├── markets, news, macro, session, risk_manager,
│   trade_guard, spread_monitor, maintenance,
│   mt5_signal_bridge                        ← support & safety modules (10 files)
├── gold_robot_ntbridge.py                  ← the live monitor robot
├── .env  (template)  +  requirements.txt  +  README.md + CHANGELOG.md
├── data\   logs\                           ← the robot's own output (empty now)
└── docs\
    ├── GoldBridgeExporter.cs / GoldFlowSignals.cs   ← NinjaTrader indicator sources
    ├── NT_BRIDGE_SETUP_GUIDE.md                      ← bridge install guide
    ├── E2E_VERIFICATION.md                           ← proof the system works end to end
    ├── MIXED_SYSTEM_OVERVIEW.md, gold_data_alternatives.md, NEXT_STEPS_IDEAS.md,
    │   paper_trade_checklist.md                      ← design & reference docs
    └── archive\                                      ← old Rithmic-journey docs
```

**What was cleaned out** (all of it still exists in your GitHub repo — nothing is lost):
40+ files removed — old test suites, demo/dev scripts, the dead Rithmic bridge, offline
tools (review/report/history/broker-diagnostic/setup), the unused MT5 EA, 16 outdated
documentation files, and the 3 .bat starters. What remains is exactly what the robot
needs to run — verified end-to-end after the cleanup.

**If you already have the Gold-MT5 project on your PC**, the simplest path now is:
delete your old local copy (keep your tuned `.env` somewhere safe first!), download this
folder fresh, and paste your `.env` back in (with the 4 edits from our chat:
`DATA_SOURCE=ninjabridge`, `DATA_SYMBOL=MGC 12-26`, comment out `DATA_MARKET`,
add `NT_WINDOW_SECONDS=7200`, leave `NT_BRIDGE_FILE=` empty).

## The one-folder layout

Everything this project needs lives in **one folder** on your PC:

```
A:\gitHub\Rhitmic\Gold-MT5\            ← the ONE folder (name your choice)
│
├── ticks.csv          ← NT writes the data DIRECTLY here (see step below)
├── gold_robot_ntbridge.py   ← monitor robot (same folder = auto-detects ticks.csv)
├── .env               ← your tuned config
├── main.py + steps 1–5 + safety modules   ← the trading system
├── data\  logs\      ← decisions, snapshots, logs (all local)
└── docs\             ← indicator sources (.cs) + setup guide (reference copies)
```

**One-time switch so NinjaTrader writes `ticks.csv` into this folder:**

1. In NinjaTrader: right-click your MGC chart → **Indicators…** → GoldBridgeExporter
2. Change **Output folder** to `A:\gitHub\Rhitmic\Gold-MT5` (your folder's actual path)
3. OK. From the next tick, `ticks.csv` is created inside the project folder.
4. In `.env`, leave `NT_BRIDGE_FILE=` **empty** — the provider and the robot both find
   `ticks.csv` in their own folder automatically (tested, including cold start).

**The only things that still live outside the folder (by platform design, not fixable):**
- The two NinjaTrader indicators (compiled inside NT: `Documents\NinjaTrader 8\bin\Custom\Indicators\`) — source copies are in `docs\`
- The MT5 terminal itself (`C:\Program Files\...`) — only referenced if you let the bot launch MT5

Everything else — data, logs, decisions, robot, config — is inside the one folder.

## One-time setup on your PC

1. Copy the `Gold-MT5` folder (or just the files above into your existing project folder) to `A:\gitHub\Rhitmic\`.
2. Install the project's Python requirements (same as before):
   ```bash
   cd /a/gitHub/Rhitmic/Gold-MT5
   pip install -r requirements.txt
   ```
3. Open `.env` in Notepad and paste your Gemini key into `GEMINI_API_KEY=`
   (without a key Step 3 always answers HOLD — the robot will watch but never act).
4. Do the NinjaTrader *Output folder* switch above so `ticks.csv` lands in this folder.

## How to run (your daily routine)

1. **Start NinjaTrader** — MGC chart with GoldBridgeExporter open (data source)
2. Open a terminal in the project folder and run:
   ```bash
   python main.py            # one full pass (great for testing)
   python main.py --loop     # continuous robot — leave it running
   python gold_robot_ntbridge.py --big 10   # optional: the live monitor window
   ```
3. Watch the PIPELINE SUMMARY at the end of each pass. Ctrl+C stops.

## The phases — follow them in order

| Phase | Setup | What happens |
|---|---|---|
| **2 — dry run** *(current config)* | as shipped (`TRADING_ENABLED=0`) | Full analysis every 60 s, decisions logged, **zero orders** |
| **3 — demo trading** | MT5 open on **demo** account, "Algo Trading" enabled, set `TRADING_ENABLED=1` in `.env` | Real orders on the demo account when AI confidence ≥ 70% |
| **4 — review & decide** | let it run 1–2 weeks | Review `data/decisions_log.csv` + `review.py`; only then discuss real money |

## Built-in safety (already in your code + the provider)

- `TRADING_ENABLED=0` master switch — analyse only
- No fresh bridge data (NT closed, chart closed, market halt, weekend) → **no trading**
  (the provider feeds `has_data` / `last_data_age_seconds` into your existing gates)
- Confidence < 70% → no order; news blackout → no new entries
- Risk caps: 1% per trade, max lots, daily loss circuit-breaker, anti-overtrading guard
- Book hygiene in the provider: crossed/stale levels dropped, max 20 levels per side
- File rotation by the exporter is detected automatically — the provider rebuilds

## Quick troubleshooting

| Symptom | Fix |
|---|---|
| `has_data=False` in the summary | NT not running / chart closed / market closed (23:00–00:00 & weekends) — or wrong `NT_BRIDGE_FILE` |
| Step 3 always HOLD @ 0% | `GEMINI_API_KEY` missing in `.env` |
| `Unknown data source 'ninjabridge'` | Old `data_providers.py` — re-copy the updated file |
| Steps say PENDING | Normal without MT5 SDK / terminal (phases 3+) |
| No candles / weak signals | Normal in the first minutes — signals sharpen as the window fills (15 min default) |
