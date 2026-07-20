# Scoring Rule Builder & Live Stat Engine — Design Spec

Approved section-by-section in conversation on 2026-07-20. Companion research: `/home/gtkacz/Codes/ftt/LIVE_SCORING_RESEARCH.md`.

## Decisions log

| Decision | Choice |
|---|---|
| Rule authoring | Two modes (weights grid + formula), one engine: both compile to a single stored formula text |
| Expression language | Arithmetic (`+ - * /`, parentheses, unary minus) plus comparisons (`< <= > >= == !=`) evaluating to 0/1. No functions, no strings, no chained comparisons |
| Engine implementation | `simpleeval` library, operator-whitelisted, `functions={}`; field names pre-validated with `ast.parse` for precise errors |
| Versioning | One mutable rule; every edit triggers full-season recompute. No version history |
| Stat corrections | Auto-apply while the game's scoring period is open (+ notification); after period close, record but never apply |
| End-of-game | Fetch immediately when ESPN flips a game to final; re-fetch every ~2 min until two consecutive identical boxes → settled. Target: minutes after the buzzer. In-game latency explicitly best-effort |
| Data source | ESPN unofficial API (verified working from the hosting network); raw JSON snapshots kept on disk |

## Scope

**In:** `scoring` Django app (models, field catalog, engine, API), ESPN ingest worker (live poll, settle, T+1 corrections sweep), minimal `ScoringPeriod`, superuser-only Vue builder UI with live preview and explicit recompute, crosswalk/backfill/parity management commands.

**Out (later specs):** matchup schedule/standings, weekly lineups, live matchup UI for regular users, PWA push.

**Invariant:** stats are facts, points are a pure function of facts. Ingest never computes points inline; recompute, corrections, and rule edits share one code path.

## Data model (`scoring` app)

- `ScoringRule` — `name`, `formula_text` (canonical), `weights_json` (nullable; only for grid-mode round-trip), `is_active` (partial unique constraint: at most one active), `updated_by`, timestamps. Formula validated on save.
- `ScoringPeriod` — `index` (unique), `starts_at`, `ends_at`, `is_closed`. Mon–Sun weeks, auto-generated; nightly close of elapsed periods.
- `NbaGame` — `espn_event_id` (unique), `starts_at`, `home`/`away` FK `NBATeam`, `status` (`scheduled|live|final|settled`), `period`, `clock`, `settle_hash`, `scoring_period` FK.
- `PlayerGameLine` — `player` FK, `game` FK (unique together), `raw_stats` JSON (complete field catalog), `fpts` Decimal(8,2), `is_final`, `updated_at`.
- `StatCorrection` — `line` FK, `field`, `old_value`, `new_value`, `applied`, `detected_at`. Every T+1 diff recorded, applied or not.
- `core.Player.espn_id` — new nullable unique field beside `nba_id`; populated by name-match crosswalk with manual fixes via Django admin.

## Field catalog (27 fields, one registry drives ingest, engine, and UI palette)

- Box atomics: `MIN PTS FGM FGA TPM TPA FTM FTA OREB DREB REB AST STL BLK TO PF PLUS_MINUS`
- Derived: `FG_MISS TP_MISS FT_MISS DD TD` (DD = ≥2 of PTS/REB/AST/STL/BLK at 10+; TD = ≥3; a triple-double also counts as DD — stacking)
- Play-by-play counters: `TF` (excludes "technical free throw" lines), `FLAGRANT`, `EJECTION`
- Context: `STARTED`, `WON` (0/1, degrade to 0 if absent — never crash)

Identifiers are valid Python names (`TPM` not `3PM`); UI may display "3PM".

## Engine semantics

- Safe division: `x / 0 → 0`, documented in the UI.
- Save/preview validation: `ast.parse` first — syntax errors with position, unknown fields with did-you-mean suggestion (difflib); then smoke-eval against all-zeros and typical lines.
- Numeric policy: evaluate in float, quantize to 2dp `ROUND_HALF_EVEN`, store `Decimal`.
- Fencing: 2,000-char formula cap, `functions={}`, operator whitelist, per-line try/except at ingest, superuser-only write endpoints.

## Pipeline

Worker (`live_scoring_worker`, same idiom as `auto_draft_picker`): scoreboard poll ~60s in game windows → live games' summaries every 20–30s → upsert lines → evaluate active rule. On `final`: immediate fetch, re-fetch ~120s until box hash stable twice → `settled`, lines `is_final`. Daily ≥10:00 BRT: corrections sweep (re-fetch last 3 days of settled games, diff, apply-if-open + notify via existing `Notification`, else record only) and period closing. Every fetch snapshotted to `MEDIA_ROOT/espn_snapshots/`.

## API (superuser-gated except catalog)

```
GET  /api/scoring/fields/                    catalog (authenticated)
CRUD /api/scoring/rules/                     superuser
POST /api/scoring/rules/preview/             {formula_text, espn_event_id} → rows | 400 {error, position, suggestion}
POST /api/scoring/rules/{id}/activate/       exclusive activate + recompute
POST /api/scoring/rules/{id}/recompute/      → {updated}
GET  /api/scoring/games/?date=YYYY-MM-DD     ingested games for preview picker (superuser)
```

## Builder UI (Vue, `/commission/scoring`, requiresStaff)

Two tabs over one rule: Grid (weight per field; compiles to formula) and Formula (text + clickable field palette + inline server errors). Rules authored in formula mode that aren't plain-linear show the grid read-only. Live preview panel: pick past date → game → per-player table (raw line, draft-rule fpts, delta vs active rule), debounced server preview. Save flow: validate → confirm dialog stating full-season recompute with line count → progress → toast.

## Testing

Django test runner (project convention). Engine grammar acceptance/rejection table; extractor tests against real recorded ESPN JSON fixtures (2026 Finals game 401859966: Julian Champagnie line, Keldon Johnson technical foul); settle state machine with mocked fetches; corrections open/closed paths; API permission and error-shape tests; recompute idempotency. Fantrax parity via `parity_check` management command against `fantrax.csv` (backfilled season, manual run — not part of the hermetic suite). 80%+ coverage on the `scoring` app.
