"""Weekly A/B validation: per-week, per-player PFF signal evaluation.

Retains weekly granularity instead of aggregating to season-level metrics.
Measures per-position rank_corr, MAE, MAE by matchup difficulty, and
WR directional accuracy for coverage signal.

Usage:
    uv run python scripts/validate_weekly_signal.py --help
    uv run python scripts/validate_weekly_signal.py --mode all --sims 50
    uv run python scripts/validate_weekly_signal.py --mode coverage+tier --positions WR
    uv run python scripts/validate_weekly_signal.py --show-ledger
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.pff.models import (
    CoverageConfig,
    MatchupConfig,
    MatchupContext,
    PffConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.weather.models import WeatherConfig
from fantasy_sim.validation.parallel import GameSpec, simulate_games_parallel, default_max_workers, build_games_parallel
from fantasy_sim.validation.weekly import (
    WeeklyLedgerEntry,
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    compute_directional_accuracy,
    compute_mae_by_difficulty,
    compute_weekly_mae,
    compute_weekly_rank_corr,
    format_weekly_progression_table,
    load_weekly_ledger,
    save_weekly_ledger,
)

POSITIONS = ("QB", "RB", "WR", "TE")

WEEKLY_LEDGER_PATH = Path(__file__).parent.parent / "results" / "weekly_ab_ledger.json"

# Position -> applicable MatchupContext fields
POSITION_MATCHUP_FACTORS: dict[str, tuple[str, ...]] = {
    "QB": ("sack_rate_factor", "int_rate_factor", "ol_pass_block_factor"),
    "RB": ("rush_yards_factor", "ol_run_block_factor"),
    "WR": ("catch_rate_factor", "pass_yards_factor"),
    "TE": ("catch_rate_factor", "pass_yards_factor"),
}


def _build_pff_config(mode: str, overrides: dict | None = None) -> PffConfig:
    """Build a PffConfig with the appropriate layers enabled.

    Args:
        mode: PFF/weather layer combination (e.g. "all", "tier", "matchup+tier").
        overrides: Optional dict with "talent" and/or "matchup" sub-dicts
            of attribute overrides to apply via setattr.
    """
    if mode == "matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "talent":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=True)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "matchup+tier":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "team_context+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=True)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "team_context+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=True)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "ncaa_rookie+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "ncaa_rookie+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "coverage+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
    elif mode == "coverage+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
    elif mode == "weather":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "weather+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    elif mode == "weather+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
    else:  # "all", "all+weather" — current defaults: tier + matchup + coverage
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)

    if overrides and "talent" in overrides:
        for key, val in overrides["talent"].items():
            if hasattr(talent_cfg, key):
                # Don't replace dataclass fields with plain dicts
                current = getattr(talent_cfg, key)
                if hasattr(current, '__dataclass_fields__') and isinstance(val, dict):
                    for k, v in val.items():
                        if hasattr(current, k):
                            setattr(current, k, v)
                else:
                    setattr(talent_cfg, key, val)
    if overrides and "matchup" in overrides:
        for key, val in overrides["matchup"].items():
            if hasattr(matchup_cfg, key):
                setattr(matchup_cfg, key, val)
    if overrides and "tier_engine" in overrides:
        for key, val in overrides["tier_engine"].items():
            if not hasattr(tier_cfg, key):
                continue
            if key == "position_grades" and isinstance(val, dict):
                # Merge per-position: only update specified positions/fields
                for pos, grade_overrides in val.items():
                    if pos in tier_cfg.position_grades and isinstance(grade_overrides, dict):
                        for gk, gv in grade_overrides.items():
                            if hasattr(tier_cfg.position_grades[pos], gk):
                                setattr(tier_cfg.position_grades[pos], gk, gv)
            else:
                current = getattr(tier_cfg, key)
                if hasattr(current, '__dataclass_fields__') and isinstance(val, dict):
                    for k, v in val.items():
                        if hasattr(current, k):
                            setattr(current, k, v)
                else:
                    setattr(tier_cfg, key, val)
    if overrides and "team_context" in overrides:
        for key, val in overrides["team_context"].items():
            if hasattr(tc_cfg, key):
                setattr(tc_cfg, key, val)
    if overrides and "ncaa_rookie" in overrides:
        ncaa_cfg = tier_cfg.ncaa_rookie
        for key, val in overrides["ncaa_rookie"].items():
            if key == "draft_confidence" and isinstance(val, dict):
                ncaa_cfg.draft_confidence = {int(k): float(v) for k, v in val.items()}
            elif hasattr(ncaa_cfg, key):
                setattr(ncaa_cfg, key, val)
    if overrides and "coverage" in overrides:
        for key, val in overrides["coverage"].items():
            if hasattr(cov_cfg, key):
                if key == "factor_clamp" and isinstance(val, list):
                    setattr(cov_cfg, key, tuple(val))
                else:
                    setattr(cov_cfg, key, val)

    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg,
                     tier_engine=tier_cfg, team_context=tc_cfg, coverage=cov_cfg)


def _build_weather_config(mode: str, overrides: dict | None = None) -> WeatherConfig | None:
    """Build a WeatherConfig if the mode includes weather.

    Returns None if weather is not part of the mode, or a WeatherConfig
    with enabled=True (and optional overrides applied) if it is.
    """
    if "weather" not in mode:
        return None

    from fantasy_sim.config.loader import load_defaults
    defaults = load_defaults()
    weather_config = load_weather_config(defaults)
    weather_config.enabled = True

    if overrides and "weather" in overrides:
        weather_raw = overrides["weather"]
        for section in ("wind", "temperature", "precipitation"):
            if section in weather_raw:
                sub_config = getattr(weather_config, section)
                for k, v in weather_raw[section].items():
                    setattr(sub_config, k, v)
        if "factor_clamp" in weather_raw:
            weather_config.factor_clamp = tuple(weather_raw["factor_clamp"])
        if "forecast_ttl_hours" in weather_raw:
            weather_config.forecast_ttl_hours = weather_raw["forecast_ttl_hours"]

    return weather_config


def _filter_matchup_factors(
    position: str, ctx: MatchupContext
) -> dict[str, float]:
    """Filter MatchupContext to position-relevant factors."""
    fields = POSITION_MATCHUP_FACTORS.get(position, ())
    return {f: getattr(ctx, f) for f in fields}


def run_weekly_comparison(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    positions: list[str],
    weather_config: WeatherConfig | None = None,
    max_workers: int = 1,
) -> list[WeeklyPlayerRecord]:
    """Run PFF-on vs PFF-off for every game in a season, collect per-player records."""

    training_seasons = list(range(
        test_season - num_training_seasons, test_season
    ))
    loader = DataLoader()
    schedules = loader.load_schedules([test_season])
    player_stats = loader.load_player_stats([test_season])

    actuals = load_actual_scores(player_stats, scoring_config, test_season)
    actual_by_pw: dict[str, dict[int, float]] = defaultdict(dict)
    actual_pos: dict[str, str] = {}
    actual_team: dict[str, str] = {}
    actual_name: dict[str, str] = {}
    for a in actuals:
        actual_by_pw[a.player_id][a.week] = a.fpts
        actual_pos[a.player_id] = a.position
        actual_team[a.player_id] = a.team
        actual_name[a.player_id] = a.name

    weeks = sorted(
        schedules.filter(pl.col("season") == test_season)["week"]
        .unique().to_list()
    )
    weeks = [w for w in weeks if 1 <= w <= 18]

    # --- Phase 1: Build all game contexts (parallel) ---
    game_args = []
    for wk in weeks:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == test_season)
        )
        print(f"  [{test_season}] Collecting games... Week {wk}/{max(weeks)}", flush=True)
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            game_args.append((
                home, away, training_seasons,
                test_season, wk, game["game_id"], seed,
            ))

    print(f"  [{test_season}] Building {len(game_args)} game contexts (workers={max_workers})...", flush=True)

    def _on_build_complete(done: int, total: int) -> None:
        if done % 20 == 0 or done == total:
            print(f"    [{test_season}] {done}/{total} games built", flush=True)

    build_results = build_games_parallel(
        game_args,
        cache_dir=loader.cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        max_workers=max_workers,
        dual_arm=True,
        on_complete=_on_build_complete,
    )

    # Assemble specs + game_aux from results
    specs: list[GameSpec] = []
    game_aux: dict[str, dict] = {}

    for r in build_results:
        if r["status"] != "ok":
            continue
        game_id = r["game_id"]
        off = r["results"]["off"]
        on = r["results"]["on"]

        specs.append(GameSpec(
            game_id=game_id,
            home_dists=off[0], away_dists=off[1],
            home_roster=off[2], away_roster=off[3],
            seed=r["seed"], week=r["week"],
            metadata={"arm": "off"},
        ))
        specs.append(GameSpec(
            game_id=game_id,
            home_dists=on[0], away_dists=on[1],
            home_roster=on[2], away_roster=on[3],
            seed=r["seed"], week=r["week"],
            metadata={"arm": "on"},
        ))

        game_aux[game_id] = {
            "home": r["home"], "away": r["away"], "week": r["week"],
            "home_matchup_ctx": r["matchup_aux"]["home_matchup_ctx"],
            "away_matchup_ctx": r["matchup_aux"]["away_matchup_ctx"],
            "home_coverage": r["matchup_aux"]["home_coverage"],
            "away_coverage": r["matchup_aux"]["away_coverage"],
        }

    # --- Phase 2: Simulate all games (parallel) ---
    print(f"  [{test_season}] Simulating {len(specs)} game-arms...", flush=True)

    def _on_complete(done: int, total: int) -> None:
        if done % 50 == 0 or done == total:
            print(f"    [{test_season}] {done}/{total} complete", flush=True)

    sim_results = simulate_games_parallel(
        specs, n_sims=n_sims, scoring_config=scoring_config,
        max_workers=max_workers, on_complete=_on_complete,
    )

    # --- Phase 3: Pair results and build records ---
    by_game: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for r in sim_results:
        by_game[r.game_id][r.metadata["arm"]] = r.projections

    records: list[WeeklyPlayerRecord] = []

    for game_id, arms in by_game.items():
        if "off" not in arms or "on" not in arms:
            continue

        aux = game_aux.get(game_id)
        if aux is None:
            continue

        home = aux["home"]
        wk = aux["week"]
        home_matchup_ctx = aux["home_matchup_ctx"]
        away_matchup_ctx = aux["away_matchup_ctx"]
        home_coverage = aux["home_coverage"]
        away_coverage = aux["away_coverage"]

        on_by_pid = {p["player_id"]: p for p in arms["on"]}
        off_by_pid = {p["player_id"]: p["fpts"] for p in arms["off"]}

        common_pids = set(on_by_pid.keys()) & set(off_by_pid.keys())

        for pid in common_pids:
            proj = on_by_pid[pid]
            pos = proj.get("position") or actual_pos.get(pid, "")
            if pos not in positions:
                continue
            if pid not in actual_by_pw or wk not in actual_by_pw[pid]:
                continue

            team = proj.get("team") or actual_team.get(pid, "")
            is_home = team == home

            matchup_ctx = home_matchup_ctx if is_home else away_matchup_ctx
            cov_map = home_coverage if is_home else away_coverage

            records.append(WeeklyPlayerRecord(
                player_id=pid,
                name=proj.get("name") or actual_name.get(pid, ""),
                position=pos,
                team=team,
                week=wk,
                season=test_season,
                projected_fpts_on=proj["fpts"],
                projected_fpts_off=off_by_pid[pid],
                actual_fpts=actual_by_pw[pid][wk],
                matchup_factors=_filter_matchup_factors(pos, matchup_ctx),
                coverage_modifiers=cov_map.get(pid) if pos == "WR" else None,
            ))

    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Weekly A/B validation: per-week PFF signal evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=[
            "matchup", "talent", "tier", "matchup+tier",
            "team_context+tier", "team_context+tier+matchup",
            "ncaa_rookie+tier", "ncaa_rookie+tier+matchup",
            "coverage+tier", "coverage+tier+matchup",
            "weather", "weather+tier", "weather+tier+matchup",
            "all", "all+weather",
        ],
        default="all",
        help=(
            "Which PFF/weather layer(s) to enable (default: all). "
            "'weather' = weather engine only, "
            "'weather+tier' = weather + tier, "
            "'weather+tier+matchup' = weather + tier + matchup."
        ),
    )
    parser.add_argument("--sims", type=int, default=50, help="Sims per game (default: 50).")
    parser.add_argument("--seasons", type=int, nargs="+", default=[2023, 2024], help="Test seasons (default: 2023 2024).")
    parser.add_argument("--training-years", type=int, default=4, dest="training_years", help="Training seasons before each test season (default: 4).")
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--positions", nargs="+", default=list(POSITIONS), help="Positions to evaluate.")
    parser.add_argument("--label", type=str, default=None, help="Label for ledger entry.")
    parser.add_argument("--show-ledger", action="store_true", help="Print ledger and exit.")
    parser.add_argument(
        "--config-override",
        type=str,
        default=None,
        dest="config_override",
        metavar="JSON",
        help='Config overrides as JSON. Keys: "talent", "matchup", "tier_engine", '
             '"team_context", "ncaa_rookie", "coverage", "weather". '
             'Example: \'{"weather": {"wind": {"pass_yards_sensitivity": 0.04}}}\'',
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Worker processes for game simulation (0=auto, 1=sequential). Default: auto.",
    )

    args = parser.parse_args()

    if args.show_ledger:
        entries = load_weekly_ledger(WEEKLY_LEDGER_PATH)
        print(format_weekly_progression_table(entries))
        return 0

    overrides = json.loads(args.config_override) if args.config_override else None
    pff_config = _build_pff_config(args.mode, overrides=overrides)
    weather_config = _build_weather_config(args.mode, overrides=overrides)

    print("=" * 68)
    print("  WEEKLY PFF SIGNAL VALIDATION")
    print("=" * 68)
    print(f"  mode          : {args.mode}")
    print(f"  sims          : {args.sims}")
    print(f"  seasons       : {args.seasons}")
    print(f"  positions     : {args.positions}")
    print(f"  training_years: {args.training_years}")
    if args.label:
        print(f"  label         : {args.label}")
    print("=" * 68)

    num_seasons = len(args.seasons)
    if args.workers == 1:
        per_season_workers = 1
    elif args.workers > 1:
        per_season_workers = args.workers
    else:
        per_season_workers = default_max_workers(batch_size=576, num_concurrent=num_seasons)
    print(f"  workers       : {per_season_workers} per season")

    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)

    total_start = time.time()
    all_records: list[WeeklyPlayerRecord] = []

    if len(args.seasons) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        print(f"\nRunning {len(args.seasons)} seasons in parallel...")
        with ProcessPoolExecutor(max_workers=len(args.seasons)) as pool:
            futures = {
                pool.submit(
                    run_weekly_comparison,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    pff_config=pff_config,
                    positions=args.positions,
                    weather_config=weather_config,
                    max_workers=per_season_workers,
                ): season
                for season in args.seasons
            }
            for future in as_completed(futures):
                season_records = future.result()
                all_records.extend(season_records)
                print(f"  Season {futures[future]}: {len(season_records)} records")
    else:
        for season in args.seasons:
            print(f"\n  [Season {season}]")
            season_records = run_weekly_comparison(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                pff_config=pff_config,
                positions=args.positions,
                weather_config=weather_config,
                max_workers=per_season_workers,
            )
            all_records.extend(season_records)

    total_elapsed = time.time() - total_start
    print(f"\nTotal time: {total_elapsed:.1f}s  |  {len(all_records)} player-week records")

    # Compute summaries
    print("\n" + "=" * 68)
    print("  WEEKLY RESULTS")
    print("=" * 68)

    summaries: list[WeeklyPositionSummary] = []
    for pos in args.positions:
        pos_records = [r for r in all_records if r.position == pos]
        if not pos_records:
            continue

        rc_on = compute_weekly_rank_corr(all_records, pos, use_pff_on=True)
        rc_off = compute_weekly_rank_corr(all_records, pos, use_pff_on=False)
        mae_on = compute_weekly_mae(all_records, pos, use_pff_on=True)
        mae_off = compute_weekly_mae(all_records, pos, use_pff_on=False)
        tercile = compute_mae_by_difficulty(all_records, pos)
        n_weeks = len({(r.season, r.week) for r in pos_records})

        summary = WeeklyPositionSummary(
            position=pos,
            weekly_rank_corr_on=rc_on,
            weekly_rank_corr_off=rc_off,
            weekly_mae_on=mae_on,
            weekly_mae_off=mae_off,
            mae_by_tercile=tercile,
            n_player_weeks=len(pos_records),
            n_weeks=n_weeks,
        )
        summaries.append(summary)

        rc_delta = rc_on - rc_off
        mae_delta = mae_on - mae_off
        print(f"\n  {pos}  ({len(pos_records)} player-weeks, {n_weeks} weeks)")
        print(f"    rank_corr: {rc_off:.4f} -> {rc_on:.4f}  (delta={rc_delta:+.4f})")
        print(f"    weekly_mae: {mae_off:.3f} -> {mae_on:.3f}  (delta={mae_delta:+.3f})")
        if tercile:
            print(f"    mae_by_difficulty: strong={tercile.get('strong', 0):.3f}  "
                  f"neutral={tercile.get('neutral', 0):.3f}  "
                  f"weak={tercile.get('weak', 0):.3f}")

    # Directional accuracy (WR only)
    dir_accuracy = None
    if "WR" in args.positions:
        actuals_by_player: dict[str, list] = defaultdict(list)
        for season in args.seasons:
            loader = DataLoader()
            player_stats = loader.load_player_stats([season])
            season_actuals = load_actual_scores(player_stats, scoring_config, season)
            for a in season_actuals:
                actuals_by_player[a.player_id].append(a)

        dir_accuracy = compute_directional_accuracy(all_records, actuals_by_player)
        print(f"\n  WR Directional Accuracy: {dir_accuracy.correct_direction}/{dir_accuracy.total_eligible} "
              f"= {dir_accuracy.accuracy:.1%}")

    print("\n" + "=" * 68)

    # Save to ledger
    if args.label:
        entry = WeeklyLedgerEntry(
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            mode=args.mode,
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            position_summaries=summaries,
            directional_accuracy=dir_accuracy,
        )
        ledger = load_weekly_ledger(WEEKLY_LEDGER_PATH)
        ledger.append(entry)
        save_weekly_ledger(WEEKLY_LEDGER_PATH, ledger)
        print(f"\n  Appended to weekly ledger as #{len(ledger)}: {args.label}")
        print(format_weekly_progression_table(ledger))

    return 0


if __name__ == "__main__":
    sys.exit(main())
