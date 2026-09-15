# Changelog

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
