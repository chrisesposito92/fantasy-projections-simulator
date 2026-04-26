# External Signal Coverage Audit

## Summary

- The single largest unrealized distribution-shape signal is **already on disk**: `~/.fantasy-sim/pff/props/props_*.parquet` carries a per-player `last_ten_json` column with the player's last 10 actual game-by-game stat outcomes (e.g. QB pass_yds: `[257, 205, 99, 264, 174, 190, 272, 316, 228, 262]`). PropsLoader/PlayerPropsEngine throw it away and only consume `consensus_line` (the mean). This is a **literal empirical sample of the player's game-level distribution** that directly addresses both QB pass_yards and WR receiving_yards KS at zero scrape cost.
- A second large unrealized signal also already on disk: `projections_json` and `averages_json` columns in the same props parquet. PFF publishes per-player **per-stat means** (passing/rushing/receiving yards, attempts, completions, TDs, INTs) plus recent-form averages. PlayerPropsEngine ignores both — it only reads `consensus_line + prop_key`. Cross-stat consistency (e.g., projected passingAttempts × completions × yards-per-attempt) is currently invisible to the engine.
- The Odds API exposes `player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate` markets. Multiple alternate yardage lines per player → a discrete CDF the simulator can target directly. We are NOT scraping these — `scripts/scrape_pff_props.py` calls only the PFF Consumer endpoint `/{season}/player-props/{week}` which returns `consensusLine` (single line, FanDuel only). The Odds API key already exists at `~/.fantasy-sim/props/.env`. Scraping the alternate-line endpoints is the highest-priority new data acquisition for KS-01 (QB pass_yards) and KS-02 (WR receiving_yards).
- Of 21 PFF facets scraped, **8 are unconsumed by any active engine**: `passing_detail` (898 cols, used only by disabled QbSplitEngine), `receiving_depth` (477 cols, used only by disabled DepthRoleEngine), `receiving_coverage`, `defense_pass_rush` (only 1 of its 38 cols read), `offense_blocking` (root-position blocking grades unused), `return_summary`, `punting_summary`, `kickoff_summary`. `passing_detail` in particular has per-zone (left/center/right × behind_los/short/medium/deep) shot-by-shot statistics — this is a **direct depth-of-target distribution per QB**, which is exactly the missing variance signal for QB pass_yards.
- Weather is fetching only `wind_speed_10m,temperature_2m,precipitation,snowfall` from Open-Meteo. **Wind direction is free** (`wind_direction_10m`), as are `wind_gusts_10m`, `relative_humidity_2m`, `dew_point_2m`, `pressure_msl`. Wind direction relative to passing axis affects the tail of QB pass_yards (deep balls into a 15+ mph headwind drop disproportionately). Currently the engine treats all wind as a scalar magnitude.

## Currently Consumed vs Available

| Source | Signal | Currently Used | Distribution-Shape Relevance | Cost |
|--------|--------|----------------|------------------------------|------|
| **PFF props parquet** `last_ten_json` | Last 10 game-level actuals per player+market | NO — `props_engine.py:142-156` only reads `consensus_line` | **Direct** — empirical CDF for player's recent distribution | $0 (cached) |
| **PFF props parquet** `projections_json` | PFF model projection means for all 12 stat categories per player | NO — only `consensus_line + prop_key` parsed | Cross-stat consistency; PFF's volume model | $0 (cached) |
| **PFF props parquet** `averages_json` | Recent-form season averages per stat | NO | Anchors recent form vs historical | $0 (cached) |
| **PFF props parquet** `option_json.payout` | Sportsbook over/under price (e.g., -198 / -112) | NO — only `consensus_line` is read | Implied probability calibration of CDF mass | $0 (cached) |
| **The Odds API** `player_pass_yds_alternate` | Multiple yardage lines + prices per QB | NO — not scraped at all | **Direct CDF** at 5-7 yardage thresholds per QB | New scraper, key exists |
| **The Odds API** `player_reception_yds_alternate` | Multiple yardage lines per WR/TE | NO | **Direct CDF** for WR receiving_yards | New scraper |
| **The Odds API** `player_rush_yds_alternate` | Multiple yardage lines per RB | NO | **Direct CDF** for RB rush_yards | New scraper |
| **The Odds API** `player_pass_attempts_alternate`, `player_receptions_alternate` | Multiple attempt/reception thresholds | NO | Discrete count distribution (KS-03, KS-04) | New scraper |
| **PFF facet** `passing_detail` | 898 cols: per-zone (left/center/right × behind_los/short/medium/deep) per-QB pass distributions, pressure splits, blitz splits, screen splits, play-action splits | Partial — only by **disabled** `QbSplitEngine` (`pff.qb_split.enabled=false`) and only for receiver efficiency factors | **Per-QB depth distribution** drives pass_yards tail | $0 (cached) |
| **PFF facet** `receiving_depth` | 477 cols: per-zone target/route/yards/YAC per WR/TE | Only by **disabled** `DepthRoleEngine` (`pff.depth_role.enabled=false`); only `total_route` aggregate | **Per-WR depth distribution** drives receiving_yards tail | $0 (cached) |
| **PFF facet** `receiving_coverage` | 40 cols: receiver vs coverage type (man/zone) — `coverage_player_id`, `targets`, `yards_after_catch`, `targeted_qb_rating` per coverage matchup | NO | Coverage-conditional WR yardage distribution | $0 (cached) |
| **PFF facet** `defense_pass_rush` | 38 cols: pass-rush win rate, pressure rate, true-pass-set splits | Only `pass_rush_win_rate` mean used in MatchupEngine z-score | Pressure rate volatility drives QB pass_yards tail (sacks=0 yd events; clean pockets=long completions) | $0 (cached) |
| **PFF facet** `offense_blocking` | 35 cols: per-OL `pbe`, `pressures_allowed`, `hits_allowed`, `sacks_allowed`, OL snap counts | Only `pbe` mean by MatchupEngine | OL volatility drives sack/clean-pocket distribution shape for QB pass_yards | $0 (cached) |
| **PFF facet** `passing_summary.avg_time_to_throw` | QB time-to-throw mean | NO (TierEngine reads only grade columns for QB) | Quick-throw QBs have tighter pass_yards distributions; long-developers have heavier tails | $0 (cached) |
| **PFF facet** `passing_summary.avg_depth_of_target` | QB aDOT | NO (TierEngine reads only grades) | aDOT directly controls pass_yards variance (deep vs short) | $0 (cached) |
| **PFF facet** `rushing_summary.breakaway_attempts`, `breakaway_yards`, `breakaway_percent`, `explosive` | RB long-run frequency | NO (TierEngine reads only grades; RbSchemeFitEngine uses direction only and is disabled) | **Direct tail** — breakaway runs drive RB rush_yards distribution skew | $0 (cached) |
| **nflverse NGS** `air_yards`, `target_separation`, `cushion`, `pacr`, `racr`, `expected_yards` | Per-player NGS metrics | Read by `usage/engine.py:497` only when `usage.ngs.enabled=true` (currently OFF; tested for rank_corr per memory) | aDOT/separation drive WR yard variance; expected_yards is variance proxy | $0 (cached) |
| **nflverse FTN charting** | Manual charting: motion, blitz, no-huddle, RPO, play-action | Read by `tracking/loader.py` only when `tracking.enabled=true` (OFF) | Personnel/scheme volatility | $0 (cached) |
| **nflverse participation** | Per-snap personnel groupings (11/12/21 etc.), defenders in box | Read by `tracking/loader.py` only when `tracking.enabled=true` (OFF) | Personnel-conditional WR/RB usage | $0 (cached) |
| **nflverse PBP** `cpoe`, `epa`, `wpa`, `success`, `qb_epa`, `air_yards`, `yards_after_catch` | Per-play advanced metrics | Used for empirical bucket sampling but **player-level CPOE/EPA/success not used by any engine** | Per-QB CPOE shifts pass_yards mean+variance simultaneously | $0 (cached) |
| **nflverse PBP** `xpass` | Expected pass probability per play | Available in PBP — NOT consumed | Game-script tail (run-out-the-clock, garbage time) | $0 (cached) |
| **nflverse player_stats** | Weekly per-player aggregates | Used in validation only (actuals); not as features | Recent-form variance | $0 (cached) |
| **Open-Meteo** `wind_direction_10m` | Wind direction (degrees) | NO — `provider.py:18` requests only `temperature_2m,wind_speed_10m,precipitation,snowfall` | Tailwind/headwind asymmetry on deep balls (QB pass_yards tail) | $0 (free, no key) |
| **Open-Meteo** `wind_gusts_10m` | Peak wind gust | NO | Variance signal (steady 15mph ≠ gusty 25mph) | $0 |
| **Open-Meteo** `relative_humidity_2m`, `dew_point_2m`, `pressure_msl` | Air density proxies | NO | Marginal — affects deep-ball flight | $0 |
| **Open-Meteo hourly** raw 3-hour values | Hourly wind/precip during 3-hour kickoff window | Averaged into scalar (`provider.py:170`) — variance discarded | Within-game weather change drives 2nd-half pass distribution | $0 |
| **PFF/nflverse** snap_counts | Snap percentages | Used by `usage/engine.py:726` and `availability/loader.py:101` only for opportunity baseline; NOT for variance modeling | Snap count variance per player → opportunity variance | $0 |
| **PFF facet** `defense_summary.qb_rating_against` | Per-defender QB rating allowed | Aggregated by MatchupEngine (DST level), not player level | Coverage-by-coverage QB pass_yards distribution | $0 |

## Hypotheses Ranked by ROI

### H-SC-01: Use PFF `last_ten_json` as a per-player empirical distribution prior

- **Source**: PFF Props (cached parquet, already on disk)
- **Signal**: `last_ten_json` column in `~/.fantasy-sim/pff/props/props_{season}_week{week:02d}.parquet`. Each row contains a JSON array of the last 10 actual game-level outcomes for the player+market (e.g., `[{"result": 257, "week": 5, "season": 2024}, ...]`).
- **Stat affected**: QB `pass_yards`, WR/TE `receiving_yards`, RB `rush_yards`, RB/WR/TE `receptions`, QB `pass_tds`, QB `pass_attempts` (all 9 prop_keys). Directly attacks KS-01, KS-02, KS-03, KS-04, KS-05, KS-06, KS-07.
- **Mechanism**: Replace the current Bayesian-blend on the **mean** (`props_engine.py:_apply_recv_yds`, `_apply_pass_yds` etc., which shift the distribution by `(blended_ratio - 1.0) * dist_mean`) with a **distribution-level blend**: form a kernel density (or empirical mix) from the 10-sample, blend with the simulator's current empirical distribution at a configurable weight, then sample from the mixture. The 10 historical results are LITERALLY samples from the player's distribution at the right time scale.
- **Currently consumed?**: No. `props_loader.py:69-94` reads parquet but never parses `last_ten_json`. `props_engine.py:142-156` only iterates over `prop_key + consensus_line`.
- **KS gain potential**: **large**. The fundamental KS issue is that the simulator's per-game receiving_yards distribution for a given WR is built from training-season aggregates and shrinks toward team/league means; the 10 most recent actuals capture role and form changes that the bucketed PBP doesn't. For QB pass_yards specifically, the mean-shift currently applied via `_apply_pass_yds` proportionally scales **all** WR/TE distributions — it changes mean but cannot widen tails.
- **rank_corr/MAE risk**: **low**. The mean of the 10-sample is close to the consensus_line; replacing a mean-only blend with a distribution-aware blend that retains the same mean keeps rank_corr stable. Tail risk: if the 10-sample is bimodal (e.g., player traded mid-season), naive blending could distort means; mitigation: weight by recency, drop samples >180 days old.
- **Effort**: 1-2 days. Add `last_ten_dist` column extraction in `props_loader.py`, add `_apply_distribution_blend` method in `props_engine.py`, add config knob `vegas.props.last_ten_weight`.
- **Dependencies**: None. Data already cached. Historical coverage caveat: only 2025 props are scraped (`props_2025_week01..18`). For 2022-2024 backtest validation, this hypothesis can only be tested on out-of-sample 2025 data, OR the props endpoint must be backfilled (see H-SC-04).

### H-SC-02: Scrape The Odds API alternate-line markets to construct a per-player CDF

- **Source**: The Odds API (https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds, key already exists at `~/.fantasy-sim/props/.env`)
- **Signal**: Markets `player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate`, `player_pass_attempts_alternate`, `player_receptions_alternate`, `player_rush_attempts_alternate`. Per The Odds API documentation, each returns multiple yardage lines per player with over/under prices (e.g., for QB Patrick Mahomes: over 200.5 @ -250, over 250.5 @ -150, over 300.5 @ +120, over 350.5 @ +400). These prices encode the market's full implied CDF.
- **Stat affected**: KS-01 (QB pass_yards), KS-02 (WR receiving_yards), KS-03 (WR receptions), KS-06 (RB rush_yards), KS-04 (TE receptions). Highest priority for QB pass_yards because passing-yards alternates typically have 5-7 lines per QB at major books.
- **Mechanism**: Convert each over price to implied probability (`prob = 100 / (price + 100)` for negative, `prob = -price / (-price + 100)` for positive), de-vig pairs (over+under → ~1.0), then construct an empirical CDF: `P(pass_yds > threshold)` for each line. Solve for the simulator's distribution that matches: scale the empirical PBP distribution variance and/or mean such that simulated `P(X > threshold)` matches the market for each line. This goes beyond Bayesian-blending the mean — it shapes the variance.
- **Currently consumed?**: No. `scripts/scrape_pff_props.py` calls only the PFF Consumer API at `https://consumer-api.pff.com/football/v3/betting/nfl/{season}/player-props/{week}` which returns `consensusLine` (single number per player+market). The Odds API integration is referenced in `INTEGRATIONS.md` ("Secondary/experimental integration; PFF props is primary") but no scraper exists.
- **KS gain potential**: **large**. This is the single most direct CDF-construction signal external to the simulator. Multiple lines = multiple equations on the distribution.
- **rank_corr/MAE risk**: **low** for line means (already covered by current consensus_line); **low to medium** for distribution shaping if implied vig is mishandled or if low-volume QBs lack alt-line coverage at minor books.
- **Effort**: **3-5 days**. (1) Write `scripts/scrape_odds_api.py` analogous to `scrape_pff_props.py` to call the alternate-line endpoint; cache as parquet at `~/.fantasy-sim/odds/`. (2) Build `OddsApiCdfLoader`. (3) Wire variance-fitting in `PlayerPropsEngine.apply()` after current mean-blend.
- **Dependencies**: API key (exists, `~/.fantasy-sim/props/.env`). The Odds API costs ~$30/mo for 50K req/mo per their pricing, well within the project's "open to paid sources" budget per PROJECT.md. Historical coverage may be limited (real-time bookmaker odds APIs typically only return current/upcoming weeks). Backfill of 2022-2024 odds data may not be available — this signal validates against future weeks of 2025/2026, not historical KS targets. Mitigation: pair with H-SC-01 which DOES have a backward-looking 10-game window per row.

### H-SC-03: Replace mean-only QB-pass-yds shift with a per-zone distribution from `passing_detail`

- **Source**: PFF (cached, `~/.fantasy-sim/pff/processed/nfl/passing_detail_*.parquet`)
- **Signal**: `passing_detail` has 898 columns per QB-game with per-zone breakdowns: `{left,center,right} × {behind_los,short,medium,deep}` for `attempts`, `completions`, `yards`, `accuracy_percent`, `qb_rating`, etc. Plus context splits: `pa_*` (play-action), `blitz_*`, `pressure_*`, `screen_*`, `npa_*`, `no_blitz_*`, `no_pressure_*`, `no_screen_*`. This is essentially a per-QB depth-of-target distribution at game grain.
- **Stat affected**: KS-01 (QB pass_yards) primarily; also KS-09 (QB pass_yards mean bias of -28 yd/game).
- **Mechanism**: For each QB, build a per-zone yards distribution from the QB's training-season `passing_detail` rows: `{deep: [yards_per_deep_attempt samples], medium: [...], short: [...], behind_los: [...]}`. Combine with the QB's per-zone attempt rate (`deep_attempts_percent`, `medium_attempts_percent`, etc.). The simulator currently treats all completions identically and uses a league-wide field-position-clamping yard model (`engine/play_resolver.py:CATCH_YARDS_BOOST=1`). A per-QB depth distribution captures both the mean (Justin Fields aDOT vs Brock Purdy aDOT) and the **variance** (deep-heavy QBs have heavier tails).
- **Currently consumed?**: No. `passing_detail` is loaded only by `QbSplitEngine` (`pff.qb_split.enabled=false`, parked) and only for **receiver efficiency factors** (`qb_split.py:47-52`), not for the QB's own per-zone distribution. The QB's depth-of-target signal in `passing_summary.avg_depth_of_target` is also not consumed by TierEngine (TierEngine reads grade columns only).
- **KS gain potential**: **large**. The current QB pass_yards distribution lacks the inter-QB variance from depth tendencies because all QBs draw yards from the same league-level depth/yards relationship. Per the `play_call_model` parked experiment in `hypotheses-list.md` ("QB pass-yards KS worsened in every tested season"), pass-volume changes alone don't fix QB pass_yards distribution shape.
- **rank_corr/MAE risk**: **medium**. Shifting QB-specific per-zone distributions could affect WR yardage too (yards = QB depth × WR completion). Must validate carefully against the constraint that high-aDOT QBs may not actually outscore low-aDOT QBs in fantasy.
- **Effort**: **5-10 days**. (1) Build `QbDepthEngine` reading per-QB zone attempts/yards from `passing_detail`. (2) Wire into `play_resolver.py` as a yards-distribution selector keyed by QB+zone instead of league-wide bucket. (3) Validate on 2022-2024 KS.
- **Dependencies**: None — data is cached. Coverage gap: QBs with <100 dropbacks in training have thin per-zone samples; mitigation: Bayesian shrinkage to position+aDOT-bucket priors.

### H-SC-04: Backfill PFF props (or The Odds API) for 2022-2024

- **Source**: PFF Consumer API (existing scraper) and/or The Odds API
- **Signal**: Historical props parquet for 2022, 2023, 2024 weeks 1-18.
- **Stat affected**: All — gates the historical KS validation of H-SC-01, H-SC-02, H-SC-03.
- **Mechanism**: Per `INTEGRATIONS.md`, props cache is "current season only". Per `AB-TESTING.md` ("`props=none` for `2022 2023 2024` is an expected result today"), historical props validation is a known coverage hole. Per `hypotheses-list.md` H-3 ("Backfill and expand historical market/props coverage"), this is already an open hypothesis; the priority is to first verify which endpoints actually return historical data (PFF Consumer's archive endpoint is undocumented).
- **Currently consumed?**: Partial. PFF props scraper works for 2025; whether `https://consumer-api.pff.com/football/v3/betting/nfl/{season}/player-props/{week}` returns 2022 data is untested in the current scraper.
- **KS gain potential**: **medium → large** (gate dependency for the larger hypotheses). On its own, just enabling current-mean Bayesian blend over historical seasons may help; the bigger lift comes when paired with H-SC-01 + H-SC-02.
- **rank_corr/MAE risk**: **low**. PFF current-season props already validated to be neutral-to-positive in `vegas.props` mode.
- **Effort**: **1 day** investigation; **2-3 days** implementation if PFF historical works; **5-10 days** if must scrape The Odds API + reconcile. PFF Consumer API may or may not allow `season=2022` queries; needs probe.
- **Dependencies**: API access to historical seasons (unknown). If PFF doesn't allow it, fallback is The Odds API (paid) — but their historical archive is also typically a paid add-on at higher tiers.

### H-SC-05: Read `projections_json` and `averages_json` JSON columns to enforce cross-stat consistency

- **Source**: PFF Props (cached)
- **Signal**: `projections_json` field in props parquet contains PFF's full per-stat model: `{"passingYards": 209.5, "passingAttempts": 28.5, "passingCompletions": 19.55, "passingTouchdowns": 1.07, "passingInterceptions": 0.57, "rushingYards": 16.52, "rushingAttempts": 3.6, "anyTimeTouchdowns": 0.27}`. Same for `averages_json` with recent-form season averages.
- **Stat affected**: QB pass_yards, pass_attempts, pass_completions, pass_tds, ints (KS-01), QB rush_yards (KS-09 indirectly), WR receiving_yards (cross-stat: yards = receptions × YPR consistency).
- **Mechanism**: Currently `PlayerPropsEngine` adjusts each stat independently (one prop_key at a time). PFF's `projections_json` provides a self-consistent multi-stat model for each player. Use the projection vector as a multi-dimensional Bayesian prior: when `pass_yards` prop and `pass_attempts` prop disagree on direction, the prior is more informative. Alternatively, use `attempts × completions/attempt × yards/completion` decomposition to constrain the QB's per-attempt yards distribution.
- **Currently consumed?**: No. `props_engine.py:151` calls `_apply_market` for each prop_key independently, never accessing `projections_json`.
- **KS gain potential**: **medium**. Smaller than H-SC-01/02/03 because most of the signal is already in the consensus_line, but cross-stat consistency reduces independent-stat regression-to-mean compression.
- **rank_corr/MAE risk**: **low**. PFF projections are professionally curated.
- **Effort**: **2-3 days**. Parse JSON columns in props_loader, add `_apply_consistent_multistat` method in props_engine.
- **Dependencies**: None.

### H-SC-06: Use `passing_summary.avg_depth_of_target` and `avg_time_to_throw` as QB-level distribution-shape priors

- **Source**: PFF (cached, `passing_summary` parquet)
- **Signal**: Per-QB-game `avg_depth_of_target` (mean throw depth) and `avg_time_to_throw` (seconds in pocket). These directly index the QB's pass distribution shape.
- **Stat affected**: KS-01 (QB pass_yards), KS-09 (QB pass_yards mean bias).
- **Mechanism**: Use the QB's training-season aDOT to scale variance of the per-pass yards distribution. High-aDOT QBs (Tua Tagovailoa, Joe Burrow when healthy) have heavier tails on pass_yards/game; low-aDOT QBs (Brock Purdy, Mac Jones) have tighter distributions. `avg_time_to_throw` adds context: longer-developing throws → bimodal distribution (deep completion or sack).
- **Currently consumed?**: No. TierEngine (`tier_engine.py:317-322`) reads `passing_summary` for QB but only for grade columns (`grades_pass`, `grades_offense`, `twp_rate`, `btt_rate`); aDOT and time-to-throw are excluded by the metadata filter.
- **KS gain potential**: **medium**. Smaller than H-SC-03 because aDOT is one summary number per QB vs full per-zone distribution, but much cheaper to wire.
- **rank_corr/MAE risk**: **low**. aDOT is well-known; using it as a variance scaler doesn't shift the mean.
- **Effort**: **1-2 days**. Add aDOT-conditional variance scaling in QB yards-distribution sampling.
- **Dependencies**: None — data is cached.

### H-SC-07: Use `rushing_summary.breakaway_*` columns to model RB rush_yards tail

- **Source**: PFF (cached, `rushing_summary` parquet)
- **Signal**: Per-RB-game `breakaway_attempts`, `breakaway_yards`, `breakaway_percent`, `explosive`. These quantify the RB's frequency of long-runs (the RB rush_yards distribution tail).
- **Stat affected**: KS-06 (RB rush_yards, currently 0.26 KS, defaults regresses vs bare).
- **Mechanism**: Currently the simulator samples rushing yards from a league-level empirical distribution per game state. Per-RB breakaway rate directly governs the tail. Add a per-RB explosive-run probability (Bayesian-shrunk to position prior with low n) and route those rushes to a dedicated long-run distribution.
- **Currently consumed?**: No. TierEngine (`tier_engine.py:317-322`) reads `rushing_summary` for RB but only for grade columns. RbSchemeFitEngine reads `rushing_direction` and `offense_run_blocking`, NOT breakaway columns. The engine is also disabled.
- **KS gain potential**: **medium**. RB rush_yards has high inter-RB tail variance (Saquon Barkley vs Najee Harris) that the league-level distribution flattens.
- **rank_corr/MAE risk**: **low to medium**. Risk of compounding with TierEngine if both adjust the rushing distribution.
- **Effort**: **2-3 days**.
- **Dependencies**: None.

### H-SC-08: Add wind direction and gusts to weather provider

- **Source**: Open-Meteo (free, no API key)
- **Signal**: `wind_direction_10m` (degrees), `wind_gusts_10m`, `relative_humidity_2m`, `dew_point_2m`, `pressure_msl`. All available as additional `hourly` parameters on the Open-Meteo archive/forecast endpoints — currently we request only `temperature_2m,wind_speed_10m,precipitation,snowfall` (`provider.py:18`).
- **Stat affected**: KS-01 (QB pass_yards) tail; secondary KS-02 (WR receiving_yards) for deep balls.
- **Mechanism**: Resolve wind direction relative to stadium passing axis (each stadium has a known field orientation). Convert to {tailwind, headwind, crosswind} components. Apply asymmetric pass_yards adjustment: 20mph headwind compresses tail more than tailwind expands it (drag is nonlinear). Gusts add variance independent of mean wind speed.
- **Currently consumed?**: No. `provider.py:170-180` averages winds over 3 hours into a scalar, no direction. `engine.py:71-78` clamps wind to [0.80, 1.20] symmetrically.
- **KS gain potential**: **small to medium**. Affects only outdoor games in windy conditions (~25% of games); within those, it shapes pass tails meaningfully.
- **rank_corr/MAE risk**: **low**. The constraint `weather neutral` per memory was about not regressing fantasy points; adding shape doesn't change means.
- **Effort**: **2 days**. Update `_HOURLY_PARAMS` in `provider.py`, add stadium orientation table to `stadiums.py`, update `WeatherContext` fields, rewire `WeatherEngine.compute_weather_factors` to use direction.
- **Dependencies**: None — Open-Meteo is free and supports these parameters out of the box.

### H-SC-09: Snap-count variance as opportunity-variance signal

- **Source**: nflverse `load_snap_counts` (cached at `~/.fantasy-sim/cache/snap_counts_*.parquet`)
- **Signal**: Per-player-week `offense_snaps`, `offense_pct`, `defense_snaps`. Variance of `offense_pct` across weeks for a player measures how predictable their snap share is — a 60%-snap player who fluctuates 40-80% has more opportunity variance than a steady 60%.
- **Stat affected**: KS-02, KS-03, KS-04, KS-05, KS-06, KS-07. Receiving and rushing yards distributions all scale with snap counts; current engine treats snap share as a point estimate.
- **Mechanism**: Compute trailing snap-pct std for each player; use as a variance multiplier on target_share/carry_share at sampling time. Currently `availability/loader.py:101` uses snap counts only to gate active/inactive; usage engine uses them for opportunity baseline only.
- **Currently consumed?**: Mean only. `usage/engine.py:726` and `availability/loader.py:101` read snap_counts but no variance is computed.
- **KS gain potential**: **medium** for WR/TE/RB receiving and rushing distributions.
- **rank_corr/MAE risk**: **low**.
- **Effort**: **2-3 days**.
- **Dependencies**: None.

### H-SC-10: Use `receiving_coverage.coverage_player_id` for per-target CB matchup conditioning

- **Source**: PFF (cached, `receiving_coverage` parquet with `coverage_player_id` field linking each WR-game to the primary defender they faced)
- **Signal**: 40-column per-target table including `targets`, `receptions`, `yards`, `yards_after_catch`, `yards_per_reception`, `targeted_qb_rating` per (WR, defender) matchup.
- **Stat affected**: KS-02 (WR receiving_yards), KS-03 (WR receptions). Goes deeper than the existing CoverageEngine which uses alignment-based CB-vs-WR pairing (RWR→LCB) at season-mean catch-rate scaling.
- **Mechanism**: The current `CoverageEngine` (`coverage.py`) determines CB matchups by alignment frequency at the season level and applies a single catch-rate factor. The actual per-game CB-WR matchup data exists in `receiving_coverage` and would shape the per-game distribution: shadow corners (Sauce Gardner) compress WR yards more than zone-heavy CBs, regardless of season-mean grade.
- **Currently consumed?**: Partial. `CoverageEngine` uses `defense_coverage_matchup` for alignment, not `receiving_coverage` for actual matchups. The engine clamps factors to [0.97, 1.03] which limits its distribution-shape impact.
- **KS gain potential**: **small to medium**. CoverageEngine is already enabled with conservative clamps; widening its impact via per-target data could shape tails but is bounded by how deterministic the CB-WR pairing is week-to-week.
- **rank_corr/MAE risk**: **medium**. Coverage matchups are noisy week-over-week.
- **Effort**: **3-5 days**.
- **Dependencies**: None.

### H-SC-11: Engage NGS `expected_yards` (xYAC, xPass) as a per-player variance signal

- **Source**: nflverse NGS (cached via `load_nextgen_stats`)
- **Signal**: NGS publishes `expected_yards`, `air_yards`, `target_separation`, `cushion`, `racr` (Receiver Air Conversion Ratio), `pacr` (Passer Air Conversion Ratio). The delta between actual and expected captures over/under-performance.
- **Stat affected**: KS-02 (WR receiving_yards), KS-01 (QB pass_yards via `pacr`).
- **Mechanism**: Per memory, NGS+route_rate were tested and kept off — but per `feedback_workflow.md`, the test was for **rank_corr**. NGS expected metrics may improve KS distribution shape without improving rank correlation, since they're variance proxies more than means.
- **Currently consumed?**: Read by `usage/engine.py:497` only when `usage.ngs.enabled=true` (currently OFF).
- **KS gain potential**: **medium**. Re-running the NGS A/B with KS as the primary metric (not rank_corr) is a low-cost test on already-implemented code.
- **rank_corr/MAE risk**: **low** (already known to be neutral-to-slightly-negative on rank_corr per memory).
- **Effort**: **<1 day** to re-validate; depends only on running existing harness with KS focus.
- **Dependencies**: None.

### H-SC-12: Use Open-Meteo hourly variance instead of 3-hour scalar mean

- **Source**: Open-Meteo
- **Signal**: Hourly raw values (already requested in API call) currently averaged at `provider.py:170-172` into scalars.
- **Stat affected**: Marginal — KS-01 in extreme weather games.
- **Mechanism**: Use min/max/std of hourly values within the kickoff+3h window as additional weather features. Currently `np.mean(winds[start_idx:end_idx])` discards variance; gusty 5-25mph mean-15 ≠ steady 15mph for tail behavior.
- **Currently consumed?**: No.
- **KS gain potential**: **small**.
- **rank_corr/MAE risk**: **low**.
- **Effort**: **1 day**.
- **Dependencies**: None.

## Cached but unused

| Cached File / Field | Used By | Status |
|---------------------|---------|--------|
| `~/.fantasy-sim/pff/props/props_*.parquet` `last_ten_json` | none | UNUSED — directly attacks KS at zero scrape cost (H-SC-01) |
| `~/.fantasy-sim/pff/props/props_*.parquet` `projections_json` | none | UNUSED (H-SC-05) |
| `~/.fantasy-sim/pff/props/props_*.parquet` `averages_json` | none | UNUSED (H-SC-05) |
| `~/.fantasy-sim/pff/props/props_*.parquet` `option_json` | none | UNUSED (price/payout encodes implied probability) |
| `~/.fantasy-sim/pff/props/props_*.parquet` `matchup_json` | none | UNUSED (small per-row JSON typically containing matchup score 1-10) |
| `passing_detail_*.parquet` (898 cols) | only disabled `QbSplitEngine` | LARGELY UNUSED — H-SC-03 |
| `receiving_depth_*.parquet` (477 cols) | only disabled `DepthRoleEngine` | LARGELY UNUSED |
| `receiving_coverage_*.parquet` (40 cols, with `coverage_player_id`) | none active (CoverageEngine uses `defense_coverage_matchup` instead) | UNUSED (H-SC-10) |
| `passing_summary.avg_depth_of_target`, `avg_time_to_throw` | none (TierEngine excludes via metadata filter) | UNUSED (H-SC-06) |
| `rushing_summary.breakaway_attempts/yards/percent`, `explosive`, `elu_rush_mtf`, `elu_yco`, `yco_attempt`, `breakaway_yards`, `scramble_yards` | TierEngine reads only grade columns | UNUSED (H-SC-07) |
| `defense_pass_rush_*.parquet` (38 cols, including `true_pass_set_*` splits) | MatchupEngine reads only `pass_rush_win_rate` mean | LARGELY UNUSED |
| `offense_blocking_*.parquet` (35 cols) | only `pbe` mean used in MatchupEngine | LARGELY UNUSED |
| `fantasy_passing_*.parquet`, `fantasy_receiving_*.parquet` | TdTendencyEngine only | Partial — many fantasy-aggregate columns not used |
| `return_summary_*.parquet`, `punting_summary_*.parquet`, `kickoff_summary_*.parquet`, `special_summary_*.parquet` | none | UNUSED (out of scope per PROJECT.md — DST/K initiative is separate) |
| `fantasy_passing.depth_aim`, `dropbacks`, `pts_per_db`, `ez_pct`, `ez_tds`, `i5_rush_*`, `rz_rush_*` | TdTendencyEngine partial | Partial |
| nflverse cached PBP `cpoe`, `xpass`, `qb_epa`, `success` per-player aggregates | none | UNUSED — already in PBP cache, no extra scrape needed |
| nflverse `load_nextgen_stats` cached data | only disabled `usage.ngs` | UNUSED (H-SC-11) |
| nflverse `load_ftn_charting` cached data | only disabled `tracking` engine | UNUSED |
| nflverse `load_participation` cached data | only disabled `tracking` engine | UNUSED |
| nflverse `load_depth_charts` (loader.py:147) | check intra-engine usage | UNUSED at engine level |
| nflverse `load_combine` | not exposed in DataLoader | NOT WIRED |

## Open questions

1. **Does the PFF Consumer API `/{season}/player-props/{week}` endpoint accept historical seasons (2022-2024)?** The current scraper only invokes 2025; needs a probe call. If yes, H-SC-04 collapses to a scrape job; if no, H-SC-04 requires The Odds API (paid backfill).
2. **Does The Odds API offer historical alternate-line data?** The Odds API's standard paid tier is real-time + 30-day archive; full historical archive is typically an enterprise upgrade. Without historical alt lines, H-SC-02 is forward-looking only and validates against 2025+ weeks, not the KS-01..KS-08 targets which are stated for 2022-2024.
3. **Are FanDuel-only props from PFF Consumer representative of the full market?** `option_json.sportsbookId` is uniformly `SDIO_FANDUEL` in cached data. If multi-book consensus has tighter lines, the variance signal may be biased. The Odds API multi-book aggregation would resolve this.
4. **Do the PFF cookie-auth game-level facets (`passing_detail`) include playoff weeks?** `scrape_pff.py:LEAGUES["nfl"].max_week=22` suggests yes (regular season ends week 18, playoffs go to 22). Validation framework currently uses regular-season weeks; tail behavior in playoffs may differ.
5. **What is the cardinality bottleneck for `passing_detail` per-zone distributions?** Backup QBs and rookies have <50 dropbacks in some zones. Need a Bayesian-shrinkage prior before this is usable for sub-tier QBs (mitigation in H-SC-03).
6. **Are last_ten_json `result` units consistent across markets?** Spot-check: pass_yd shows integer yards (257, 205, 99). Need to confirm receptions = integer count, rushing yards = integer yards, passing TDs = integer count, anytime_td = 0/1. Schema is implicit in PFF output; documentation gap.
7. **For backfill via The Odds API, is the "historical odds API" cost separate from the live API?** Their pricing page distinguishes live/archive; estimate is ~$50-150/mo for full historical access at the relevant sport tier.
8. **Should `vegas.props` engine continue to be PFF-primary or pivot to The Odds API?** PFF gives 1 line per market but rich JSON metadata; The Odds API gives multi-line (CDF-shaping) but no `last_ten_json`. They are **complementary**: PFF for distribution priors (H-SC-01, H-SC-05), The Odds API for variance shaping (H-SC-02). Recommendation: run both, keep PFF as the consensus_line source and use The Odds API only for alt-line CDFs.

## Sources

- [The Odds API — Betting Markets](https://the-odds-api.com/sports-odds-data/betting-markets.html)
- [The Odds API — NFL Odds](https://the-odds-api.com/sports/nfl-odds.html)
- [The Odds API V4 Documentation](https://the-odds-api.com/liveapi/guides/v4/)
