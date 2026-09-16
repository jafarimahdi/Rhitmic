# Changelog

## 2026-09-16 — v4.4: measurable trading (backtest + trade memory + adaptive defense)

The institutional review found the robot's strategy logic sound but its
PROCESS behind: no backtesting, no trade memory, no kill switch, and
entry guards that trusted the signal layer too much. v4.4 closes those
gaps in four phases. Every new feature is default-safe: on a fresh
robot with no losses and no macro read, behavior is identical to v4.3.2
(battery 7 proves it — 43/43).

**P1 — entry quality guards (step4_mt5_execution.py)**
- REAL RISK GUARD: refuses an entry whose actual dollar risk (lots x
  stop distance x contract size) exceeds ENTRY_MAX_REAL_RISK_PCT (1.5%)
  of equity. This is what protects small accounts when the broker's
  minimum lot (0.01) is bigger than RISK_PER_TRADE_PCT wanted.
- COST GUARD: refuses an entry whose TP distance is below
  ENTRY_MIN_TP_SPREAD_MULT (3) spreads — a target that cannot pay the
  toll is not a target.
- Signal thresholds and ALL vote weights moved from code constants to
  .env (SIGNAL_BUY_THRESHOLD, SIGNAL_SELL_THRESHOLD, SIGNAL_W_*).
  Defaults are the same numbers the code always used — nothing changes
  until you edit them. This is the dial set for the vote/weights tuning
  session.

**P2 — backtest harness (tools/backtest.py + docs/BACKTEST.md)**
Replays a recorded ticks.csv through the REAL Step 2 engine and the
REAL PositionManager on an event-time clock (no live files touched:
state, journal and trade memory are redirected into the report folder).
Outputs trades.csv + summary (win rate, expectancy, profit factor, max
drawdown, PM rule frequencies). AI is OFF in replay (deterministic
score gate) and the report says so. For exact reproducibility run with
PYTHONHASHSEED=0.

**P3 — trade memory + adaptive defense (trade_history.py, new)**
- data/trade_memory.json: rolling ~200 closed trades, each joined with
  its entry context (AI confidence, signal strength). data/tca_log.csv:
  intended vs actual fill price (slippage) for every entry and exit.
- LOSS MEMORY: after a losing trade in direction X, signals in the same
  direction must score ENTRY_LOSS_MEMORY_SCORE_PENALTY (5) points higher
  for ENTRY_LOSS_MEMORY_MINUTES (30). Don't poke the same fire twice.
- DAY RATCHET: on a losing day the entry bar rises: -1% -> +5 points,
  -2% -> +10 (protects the daily-loss halt budget).
- PARTIAL EXITS: at +PM_PARTIAL_TRIGGER_R (1.0R) the PM banks half the
  position at market and lets the runner ride with the ratchet.
  Positions too small to split (0.01 lots) skip this automatically.
- REGIME-ADAPTIVE LOCK: when Step 2 says RANGE, the profit ratchet arms
  earlier (0.75 x ATR) and gives back less (40%).
- MACRO DEFENSE: when the macro backdrop (DXY/yields/VIX) fights the
  position by >= PM_MACRO_OPP_THRESHOLD (0.3), same tighter treatment.
  The bias travels on the new snapshot field macro_bias (-1..+1).
- GONE-POSITION DETECTION: a position that vanishes between cycles (SL/TP
  hit at the broker) is now recorded via MT5 deal history (exact PnL) —
  this is what makes loss memory complete.

**P4 — observability + kill switch**
- PAUSE FILE: create a file named PAUSE next to main.py -> new entries
  stop (AI + Step 4 skipped, saving AI quota); open positions keep being
  managed and monitoring keeps running. Delete the file to resume.
- TCA logging wired into step4 entries, PM closes and partial closes.
- PM journal rows are now timestamped (was an empty column since v4).

**Files changed:** config.py, step2_market_analysis.py,
step4_mt5_execution.py, position_manager.py, main.py,
.env.example, CHANGELOG.md, docs/POSITION_MANAGER.md,
docs/BACKTEST.md (new), trade_history.py (new), tools/backtest.py (new).

**Tests (battery 7, 43 checks):** PM core regression (ratchet, momentum
exit, time stop, flip exit, cooldown, tighten-only) + partial exits +
regime/macro adaptive lock + loss memory/day ratchet + gone detection +
TCA + .env weight plumbing + step4 guards through the full execute()
path + backtest harness end-to-end on 113k synthetic events. Compile-all
clean; full pipeline run clean.


## 2026-09-15 — v4.3.2: Gemini key slots up to 20

The user added a 6th key — the old code only read GEMINI_API_KEY_2.._5,
so key #6 was silently ignored. The key list is now built dynamically:
GEMINI_API_KEY_2 ... GEMINI_API_KEY_20 are all read automatically, empty
slots are skipped, rotation order stays numeric. Adding a key to .env
still takes effect without a restart (hot reload each cycle).


## 2026-09-15 — v4.3.1 hotfix: the tick window was capped at ~1 minute

Live log evidence: loop iteration 98 (~3 h uptime, 1.6M bridge lines
seen) still showed "200 ticks, 2 M1 bars" — the candle window never
grew. Root cause: `_prune_old_ticks` in `ninja_bridge_provider.py` had
its two branches inverted. When ALL ticks were fresh (the normal case
with NT_WINDOW_SECONDS=28800), it fell into the market-halt branch and
truncated the window to the last 200 ticks. Consequences: candle
history permanently ~2 M1 bars -> ATR 0 every cycle (the real root
cause behind the 0.5% emergency stop fallback), MTF / order blocks /
HTF POC idle forever, VWAP/POC computed on ~1 minute of data.

Fixed: stale head is dropped, halt keeps last 200, a full-fresh window
is kept whole. With NT_WINDOW_SECONDS=28800 the robot now holds up to
8 h of trades (~480 M1 bars) and the 64 MB catch-up backfills ~1-2 h
of history instantly on restart. 6 new tests (T35-T40, battery 6).


## 2026-09-15 — v4.3 profit protection (from live observation)

Watched live: a +$8 SELL whose SL stayed behind entry, and a TP that
adapted but couldn't capture the turn. Two rules and one root-cause fix:

- **PROFIT_LOCK (ratchet)**: once the open gain reaches 1xATR, the SL
  never gives back more than PM_PROFIT_GIVEBACK (50%) of the BEST gain
  seen. Winners close as winners — the exact "come back and close in
  profit, not negative" behaviour requested.
- **MOMENTUM_EXIT**: a profitable position whose momentum visibly rolls
  over (flow health "against" + composite signal >= 40 against, armed at
  >= 0.3R best) closes AT MARKET immediately — no waiting for the TP to
  be touched, no giving profit back to the trailing stop.
- **ATR ladder (step 2)**: on a fresh/shallow bridge file the M1 ATR is
  now estimated from the mean M1 range or the tick range instead of
  collapsing to 0 — entry stops, buffers and every distance-based rule
  keep their true scale right after an NT restart (this was the hidden
  reason the observed stop was so slow to move).
- 12 new tests (82 total for the manager, all passing).


## 2026-09-15 — v4.2 risk perimeter

Protection against the three things no stop-loss can save you from:

- **NEWS_PROTECT / NEWS_FLATTEN**: a HIGH-impact event (CPI/NFP/FOMC)
  within PM_NEWS_PROTECT_MINUTES (10) now protects open positions —
  default mode "tighten" locks the gains of profitable trades (losers
  keep their structural stop: tightening into pre-news noise feeds the
  hunt); "flatten" mode closes everything before the release.
- **SESSION_FLATTEN**: at PM_DAILY_FLATTEN_UTC (21:30) every bot position
  closes BEFORE the XAUUSD CFD daily break — a gap can jump straight over
  a stop, so the only real protection is being flat. Covers Friday too.
- **Spread guard**: SL/TP edits and non-urgent closes are postponed while
  the CFD spread exceeds PM_ACTION_MAX_SPREAD_PCT (0.05%) — never donate
  a news-second spread. Urgent closes (flattens) still execute.
- **Flow memory**: the CVD/price history persists in pm_state.json, so
  flow-health classification no longer needs a warm-up after restarts.
- 18 new sandbox tests (70 total for the manager, all passing).

## 2026-09-15 — v4.1.1 startup-history fix (from live log review)

First live run of v4.1 revealed the candle-based features were starving:
the NT bridge tailer only re-read the **last 10 MB** of ticks.csv on start,
which on a busy news day (CPI burst) covered just minutes — so ATR was 0,
MTF / order blocks / H1-H4 POC stayed idle and the position manager had to
use its 0.5% ATR fallback (which is why a far SL was not tightened).

- `NT_CATCHUP_MB` (default 64, in `.env`): how many MB of ticks.csv to
  re-read at startup — several hours of history, so ATR/MTF/order blocks/
  HTF POC work immediately after a restart.
- Step 2 now prints a visible note `candle history shallow (N M1 bars)`
  while the history is too short, so it is obvious when it has healed.

## 2026-09-15 — v4.1 in-trade intelligence

The five tools now work DURING the trade, not just at entry:

- **HTF POC**: Step 2 attaches `htf_poc` (H1 + H4 volume-profile Points of
  Control, from the trailing 60/240 M1 bars). The big-timeframe magnets
  join the SL anchor and TP target pools.
- **Footprint zones**: stacked-imbalance clusters (one side dominating
  3:1+ over ≥3 consecutive prices with real volume) are extracted live
  from the footprint's per-price volumes and act as fresh demand/supply.
- **Flow health (CVD)**: the manager keeps a rolling CVD/price history and
  classifies the move each cycle. When price moves in the trade's favour
  but CVD disagrees ("aggressors exhausted"), the break-even trigger drops
  from 1.0R to 0.5R. The classification and its next-step guess is logged.
- **VWAP regime**: trend side (z ≥ 0.5) → SL trails behind VWAP; stretched
  (z ≥ 2.0) → lock half the open gain; range day → VWAP becomes a TP magnet.
- All new behaviour is tighten/protect/exit only — never a new trade, never
  a wider stop. Every level now carries its source ("order block",
  "footprint imbalance", "H4 POC", ...) into the logs.
- 16 new sandbox tests (52 total for the manager, all passing) incl. a
  synthetic 8h session verifying H1/H4 POC against a planted volume node.

## 2026-09-15 — v4 trade management ("no more open-and-forget")

**New: `position_manager.py`** — the robot now manages open positions.

- **Structural SL/TP at entry** (replaces blind 1.5×/3.0×ATR): SL placed
  beyond order-block zones / POC / strong round numbers with a buffer and
  hunt-protection (never parked just above x00/x50); TP placed in front of
  opposing structure so we exit where the big traders bank profit.
  Distances clamped to [1.2, 3.0]×ATR — fixes stops being too far.
- **Open-position management every cycle**: adopts existing positions
  (magic 234000 only; manual trades untouched), tightens far stops
  (ADOPT_TIGHTEN), moves to break-even at +1R, trails behind fresh
  structure (tighten-only), updates TP to front-run new opposing levels,
  and closes early on signal flip (flow-confirmed), CVD divergence, or a
  dead-trade time stop.
- **Safety**: SL can never widen; one edit per position per 180s
  (exits exempt); broker stop-level respected; errors contained.
- **Audit trail**: every management action + reason journaled to
  `data/management_log.csv`; per-position state persists across restarts
  (`data/pm_state.json`).
- All settings tunable via `PM_*` keys in `.env` (see
  `docs/POSITION_MANAGER.md`). Verified with 36 sandbox tests incl. SELL
  mirror, futures→CFD scaling and full pipeline pass.

## 2026-09-15 — v3 "gold-native" analysis engine
- Macro votes are now **change-based** (Δ 10Y yields / Δ DXY over 5 sessions,
  VIX vs its 20-session median) + the **macro-opposition rule**: opposition
  shrinks the score up to −50%; extreme opposition without order-flow
  confirmation caps the signal to NEUTRAL ("fight the macro only with flow").
- **MTF revival**: M1 candles resampled into M5/M15/H1 (≥20 bars each) —
  higher-timeframe confirmation without a second data source.
- **Round-number 3-state votes** (x00=1.0 / x50=0.8 / x25=0.6 / x10=0.4 tiers):
  magnet on approach, follow-flow at the level, continuation only on a
  flow-confirmed break, snapback on a failed one.
- **Asian-range box + London-morning breakout** vote (08:00–12:00 UTC).
- Volume-regime switch for the VWAP mean-reversion fade (uses volatility_rank).
- Order-flow delta is volume-relative (buy% − sell%) — thin markets can no
  longer produce full-strength votes.
- Divergence lookback 5 → 15 candles; news sentiment 0.7 → 0.4; MACD 0.8 → 0.6;
  microprice 0.3 → 0.5.
- Candle builder drops empty minutes (fixes the overnight NaN crash).
- Executor hardening: real-account guard (ALLOW_LIVE_TRADING) + broker-side
  CFD spread check right before ordering.
- E2E verification report: docs/E2E_VERIFICATION.md · decision framework:
  docs/DECISION_CHAIN.md · market-driver rationale: docs/GOLD_MARKET_DRIVERS.md

## 2026-09-14 — mixed-platform consolidation (Phase 1 complete)
- One-folder layout: the NinjaTrader exporter writes ticks.csv directly into
  the project folder; all paths localized.
- NinjaBridgeProvider: 10MB catch-up, rotation-safe tailer, 20-level book,
  window pruning (NT_WINDOW_SECONDS), cold-start safe.
- gold_robot_ntbridge.py v3.4 monitor robot (auto-detect bridge file).
- Safety audit: 18 executor gates, single-instance lock, daily-loss and
  max-drawdown circuit breakers, cooldown + daily cap (persisted).
- First full live run verified end-to-end (34k ticks, Gemini multi-key
  rotation surviving 503s).
- Cleanup: 66 → 19 runtime files (full history preserved in git).
