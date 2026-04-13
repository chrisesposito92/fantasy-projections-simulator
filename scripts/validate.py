"""Unified A/B validation script.

Replaces validate_pff_signal.py and validate_weekly_signal.py.
Runs Arm A (bare baseline or defaults) vs Arm B (defaults + overrides)
and reports season-level and/or weekly metrics.

Usage:
    uv run python scripts/validate.py --help
    uv run python scripts/validate.py --sims 50 --label "baseline-v1"
    uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "test-ngs"
    uv run python scripts/validate.py --sims 50 --baseline defaults --set usage.ngs.enabled=true
    uv run python scripts/validate.py --show-ledger
"""

from __future__ import annotations

import argparse
import sys
import time
import zlib
from collections.abc import Mapping
from collections import defaultdict
from datetime import datetime
import numpy as np
import polars as pl

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.ensemble import EnsembleConfig, load_ensemble_config
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
from fantasy_sim.validation.coverage import SignalCoverage, collect_signal_coverage
from fantasy_sim.validation.cache import cache_path, load_cache, save_cache
from fantasy_sim.validation.config import (
    apply_overrides,
    build_bare_engine_configs,
    build_engine_configs,
)
from fantasy_sim.validation.ledger import (
    CURRENT_LEDGER_SCHEMA_VERSION,
    DEFAULT_LEDGER_PATH,
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)
from fantasy_sim.validation.metrics import boom_bust_calibration, spearman_rank_correlation
from fantasy_sim.validation.parallel import (
    GameSpec,
    build_games_parallel,
    default_max_workers,
    simulate_games_parallel,
)
from fantasy_sim.validation.game_script import (
    collect_game_script_profiles,
    format_game_script_summary,
)
from fantasy_sim.validation.weekly import (
    DirectionalAccuracyResult,
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    compute_directional_accuracy,
    compute_mae_by_difficulty,
    compute_weekly_mae,
    compute_weekly_rank_corr,
)

POSITIONS = ("QB", "RB", "WR", "TE")
_HOLDOUT_SEASON = 2025
SEED_MODE = "deterministic_game_id_crc32_shared_between_arms"

# Position -> applicable MatchupContext fields (same as old weekly script)
POSITION_MATCHUP_FACTORS: dict[str, tuple[str, ...]] = {
    "QB": ("sack_rate_factor", "int_rate_factor", "ol_pass_block_factor"),
    "RB": ("rush_yards_factor", "ol_run_block_factor"),
    "WR": ("catch_rate_factor", "pass_yards_factor"),
    "TE": ("catch_rate_factor", "pass_yards_factor"),
}


def _filter_matchup_factors(position: str, ctx: object) -> dict[str, float]:
    """Filter MatchupContext to position-relevant factors."""
    fields = POSITION_MATCHUP_FACTORS.get(position, ())
    return {f: getattr(ctx, f, 1.0) for f in fields}


def _comparison_mode(baseline: str) -> str:
    return "marginal_lift" if baseline == "defaults" else "total_lift"


def _format_coverage_line(
    coverage_summary: Mapping[str, SignalCoverage] | None,
) -> str:
    if not coverage_summary:
        return ""

    parts: list[str] = []
    for name in sorted(coverage_summary):
        signal = coverage_summary[name]
        if not signal.enabled:
            status = "disabled"
        else:
            status = signal.status
        if signal.covered_seasons:
            seasons = ",".join(str(season) for season in signal.covered_seasons)
            parts.append(f"{name}={status}({seasons})")
        else:
            parts.append(f"{name}={status}")
    return "  coverage   : " + " | ".join(parts)


def _format_coverage_notes_line(
    coverage_summary: Mapping[str, SignalCoverage] | None,
) -> str:
    if not coverage_summary:
        return ""

    parts: list[str] = []
    for name in sorted(coverage_summary):
        signal = coverage_summary[name]
        if signal.status not in {"none", "partial"}:
            continue
        if not signal.note:
            continue
        note = signal.note.replace("Requires ", "").replace("requires ", "")
        parts.append(f"{name}:{signal.status} {note}")
    return "  coverage notes: " + " | ".join(parts) if parts else ""


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "A/B validation: compare Arm A (bare baseline or defaults) vs "
            "Arm B (defaults + overrides)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        dest="overrides",
        metavar="KEY=VALUE",
        help=(
            "Dot-notation config override applied to Arm B. Repeatable. "
            "Example: --set pff.matchup.enabled=false --set usage.ngs.enabled=true"
        ),
    )
    parser.add_argument(
        "--baseline",
        choices=["bare", "defaults"],
        default="bare",
        help="Arm A config: 'bare' (all engines off, default) or 'defaults' (defaults.yaml as-is).",
    )
    parser.add_argument("--sims", type=int, default=50, metavar="N", help="Sims per game (default: 50).")
    parser.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024], metavar="YEAR")
    parser.add_argument("--training-years", type=int, default=4, dest="training_years", metavar="N")
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--positions", nargs="+", default=list(POSITIONS))
    parser.add_argument("--label", type=str, default=None, help="Label for ledger entry.")
    parser.add_argument("--show-ledger", action="store_true", help="Print ledger and exit.")
    parser.add_argument("--workers", type=int, default=0, metavar="N", help="Workers (0=auto, 1=sequential).")
    parser.add_argument("--no-cache", action="store_true", dest="no_cache", help="Skip bare baseline cache.")
    return parser


def run_season(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    arm_a_configs: dict,
    arm_b_configs: dict,
    arm_a_ensemble_config: EnsembleConfig | None = None,
    arm_b_ensemble_config: EnsembleConfig | None = None,
    positions: list[str] | None = None,
    max_workers: int = 1,
    cached_arm_a: dict | None = None,
) -> dict:
    """Run A/B comparison for one season.

    Args:
        arm_a_configs: Dict of engine config kwargs (pff_config, weather_config, etc.) or all None.
        arm_b_configs: Dict of engine config kwargs for Arm B.
        cached_arm_a: Pre-loaded cache dict with 'projections' and 'player_meta', or None.

    Returns:
        Dict with 'season_metrics', 'weekly_records' (if applicable),
        and 'arm_a_projections'/'arm_a_meta' (for cache saving).
    """
    training_seasons = list(range(test_season - num_training_seasons, test_season))
    positions = positions or list(POSITIONS)
    arm_a_ensembler = (
        FfOpportunityProjectionEnsembler(arm_a_ensemble_config)
        if (
            arm_a_ensemble_config is not None
            and arm_a_ensemble_config.enabled
            and arm_a_ensemble_config.ff_opportunity.enabled
        )
        else None
    )
    arm_b_ensembler = (
        FfOpportunityProjectionEnsembler(arm_b_ensemble_config)
        if (
            arm_b_ensemble_config is not None
            and arm_b_ensemble_config.enabled
            and arm_b_ensemble_config.ff_opportunity.enabled
        )
        else None
    )
    arm_a_role_trend = (
        RoleTrendProjectionAdjuster(arm_a_configs["role_trend_config"])
        if arm_a_configs.get("role_trend_config") is not None
        else None
    )
    arm_b_role_trend = (
        RoleTrendProjectionAdjuster(arm_b_configs["role_trend_config"])
        if arm_b_configs.get("role_trend_config") is not None
        else None
    )
    arm_a_market_history = (
        MarketHistoryProjectionAdjuster(
            arm_a_configs["market_history_config"],
            scoring_config=scoring_config,
        )
        if arm_a_configs.get("market_history_config") is not None
        else None
    )
    arm_b_market_history = (
        MarketHistoryProjectionAdjuster(
            arm_b_configs["market_history_config"],
            scoring_config=scoring_config,
        )
        if arm_b_configs.get("market_history_config") is not None
        else None
    )

    arm_a_build_configs = {
        key: value
        for key, value in arm_a_configs.items()
        if key not in {"role_trend_config", "market_history_config"}
    }
    arm_b_build_configs = {
        key: value
        for key, value in arm_b_configs.items()
        if key not in {"role_trend_config", "market_history_config"}
    }

    loader = DataLoader()
    schedules = loader.load_schedules([test_season])
    player_stats = loader.load_player_stats([test_season])
    actuals = load_actual_scores(player_stats, scoring_config, test_season)

    # Index actuals
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
        schedules.filter(pl.col("season") == test_season)["week"].unique().to_list()
    )
    weeks = [w for w in weeks if 1 <= w <= 18]

    # Build game args
    game_args = []
    for wk in weeks:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == test_season)
        )
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            game_args.append((home, away, training_seasons, test_season, wk, game["game_id"], seed))

    # --- Build + simulate ---
    arm_a_proj: dict[str, dict[int, float]] = {}
    arm_a_meta: dict[str, dict] = {}
    specs_b: list[GameSpec] = []
    # matchup_data: (team, week) -> {matchup_ctx, coverage} — populated by dual-arm builds only
    matchup_data: dict[tuple[str, int], dict] = {}

    if cached_arm_a is not None:
        # Arm A from cache -- only build and simulate Arm B
        arm_a_proj = cached_arm_a["projections"]
        arm_a_meta = cached_arm_a["player_meta"]
        print(f"  [{test_season}] Arm A loaded from cache", flush=True)

        print(f"  [{test_season}] Building {len(game_args)} Arm B game contexts...", flush=True)
        build_results = build_games_parallel(
            game_args, cache_dir=loader.cache_dir,
            max_workers=max_workers, dual_arm=False,
            **arm_b_build_configs,
        )
        for r in build_results:
            if r["status"] != "ok":
                continue
            specs_b.append(GameSpec(
                game_id=r["game_id"], home_dists=r["home_dists"],
                away_dists=r["away_dists"], home_roster=r["home_roster"],
                away_roster=r["away_roster"], seed=r["seed"], week=r["week"],
            ))

        print(f"  [{test_season}] Simulating {len(specs_b)} Arm B games...", flush=True)
        sim_b = simulate_games_parallel(
            specs_b, n_sims=n_sims, scoring_config=scoring_config,
            max_workers=max_workers,
        )

        # Index Arm B projections
        arm_b_proj: dict[str, dict[int, float]] = defaultdict(dict)
        arm_b_meta: dict[str, dict] = {}
        spec_by_id_b = {s.game_id: s for s in specs_b}
        for result in sim_b:
            spec = spec_by_id_b[result.game_id]
            projections = apply_projection_layers(
                result.projections,
                season=test_season,
                week=spec.week,
                role_trend_adjuster=arm_b_role_trend,
                market_history_adjuster=arm_b_market_history,
                ensembler=arm_b_ensembler,
            )
            for proj in projections:
                pid = proj["player_id"]
                arm_b_proj[pid][spec.week] = proj["fpts"]
                if pid not in arm_b_meta:
                    arm_b_meta[pid] = {
                        "position": proj.get("position", actual_pos.get(pid, "")),
                        "team": proj.get("team", actual_team.get(pid, "")),
                        "name": proj.get("name", actual_name.get(pid, "")),
                    }

    else:
        # No cache -- determine build strategy
        arm_a_is_bare = all(v is None for v in arm_a_configs.values())

        if arm_a_is_bare:
            # Bare baseline: use dual-arm build (shares data loading)
            print(f"  [{test_season}] Building {len(game_args)} game pairs (dual-arm)...", flush=True)
            build_results = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=True,
                pff_config=arm_b_configs.get("pff_config"),
                weather_config=arm_b_configs.get("weather_config"),
                vegas_config=arm_b_configs.get("vegas_config"),
                props_config=arm_b_configs.get("props_config"),
                availability_config=arm_b_configs.get("availability_config"),
                usage_config=arm_b_configs.get("usage_config"),
                game_script_config=arm_b_configs.get("game_script_config"),
                goal_line_concentration_config=arm_b_configs.get(
                    "goal_line_concentration_config"
                ),
                td_tendency_config=arm_b_configs.get("td_tendency_config"),
            )

            specs_a: list[GameSpec] = []
            for r in build_results:
                if r["status"] != "ok":
                    continue
                off = r["results"]["off"]
                on = r["results"]["on"]
                specs_a.append(GameSpec(
                    game_id=r["game_id"], home_dists=off[0], away_dists=off[1],
                    home_roster=off[2], away_roster=off[3],
                    seed=r["seed"], week=r["week"], metadata={"arm": "a"},
                ))
                specs_b.append(GameSpec(
                    game_id=r["game_id"], home_dists=on[0], away_dists=on[1],
                    home_roster=on[2], away_roster=on[3],
                    seed=r["seed"], week=r["week"], metadata={"arm": "b"},
                ))
                # Collect matchup/coverage aux for weekly metrics
                aux = r.get("matchup_aux", {})
                if aux:
                    wk = r["week"]
                    matchup_data[(r["home"], wk)] = {
                        "matchup_ctx": aux.get("home_matchup_ctx"),
                        "coverage": aux.get("home_coverage", {}),
                    }
                    matchup_data[(r["away"], wk)] = {
                        "matchup_ctx": aux.get("away_matchup_ctx"),
                        "coverage": aux.get("away_coverage", {}),
                    }

            all_specs = specs_a + specs_b

        else:
            # --baseline defaults: two separate single-arm builds
            print(f"  [{test_season}] Building {len(game_args)} Arm A game contexts...", flush=True)
            build_a = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=False, **arm_a_build_configs,
            )
            print(f"  [{test_season}] Building {len(game_args)} Arm B game contexts...", flush=True)
            build_b = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=False, **arm_b_build_configs,
            )

            specs_a = []
            for r in build_a:
                if r["status"] != "ok":
                    continue
                specs_a.append(GameSpec(
                    game_id=r["game_id"], home_dists=r["home_dists"],
                    away_dists=r["away_dists"], home_roster=r["home_roster"],
                    away_roster=r["away_roster"],
                    seed=r["seed"], week=r["week"], metadata={"arm": "a"},
                ))
            for r in build_b:
                if r["status"] != "ok":
                    continue
                specs_b.append(GameSpec(
                    game_id=r["game_id"], home_dists=r["home_dists"],
                    away_dists=r["away_dists"], home_roster=r["home_roster"],
                    away_roster=r["away_roster"],
                    seed=r["seed"], week=r["week"], metadata={"arm": "b"},
                ))

            all_specs = specs_a + specs_b

        print(f"  [{test_season}] Simulating {len(all_specs)} game-arms...", flush=True)
        sim_all = simulate_games_parallel(
            all_specs, n_sims=n_sims, scoring_config=scoring_config,
            max_workers=max_workers,
        )

        # Split results by arm
        arm_a_proj = defaultdict(dict)
        arm_b_proj = defaultdict(dict)
        arm_a_meta = {}
        arm_b_meta = {}

        spec_by_id_a = {s.game_id: s for s in specs_a}
        spec_by_id_b = {s.game_id: s for s in specs_b}

        for result in sim_all:
            is_arm_a = result.metadata.get("arm") == "a"
            spec = spec_by_id_a[result.game_id] if is_arm_a else spec_by_id_b[result.game_id]
            ensembler = arm_a_ensembler if is_arm_a else arm_b_ensembler
            role_trend_adjuster = arm_a_role_trend if is_arm_a else arm_b_role_trend
            market_history_adjuster = (
                arm_a_market_history if is_arm_a else arm_b_market_history
            )
            projections = apply_projection_layers(
                result.projections,
                season=test_season,
                week=spec.week,
                role_trend_adjuster=role_trend_adjuster,
                market_history_adjuster=market_history_adjuster,
                ensembler=ensembler,
            )
            proj_dict = arm_a_proj if is_arm_a else arm_b_proj
            meta_dict = arm_a_meta if is_arm_a else arm_b_meta
            for proj in projections:
                pid = proj["player_id"]
                proj_dict[pid][spec.week] = proj["fpts"]
                if pid not in meta_dict:
                    meta_dict[pid] = {
                        "position": proj.get("position", actual_pos.get(pid, "")),
                        "team": proj.get("team", actual_team.get(pid, "")),
                        "name": proj.get("name", actual_name.get(pid, "")),
                    }

    if arm_b_configs.get("game_script_config") is not None:
        profiles = collect_game_script_profiles(specs_b)
        if profiles:
            print(format_game_script_summary(profiles), end="", flush=True)

    # --- Compute season-level metrics ---
    def _compute_arm_metrics(
        proj_by_pw: dict[str, dict[int, float]],
    ) -> tuple[float, float, dict[str, float], float]:
        """Returns (weekly_mae, season_mae, rank_corr_by_pos, calibration)."""
        all_errors = []
        for pid, pw in proj_by_pw.items():
            for wk, fpts in pw.items():
                if pid in actual_by_pw and wk in actual_by_pw[pid]:
                    all_errors.append(abs(fpts - actual_by_pw[pid][wk]))
        weekly_mae = float(np.mean(all_errors)) if all_errors else 99.0

        proj_totals = {pid: sum(wks.values()) for pid, wks in proj_by_pw.items()}
        act_totals = {pid: sum(wks.values()) for pid, wks in actual_by_pw.items()}
        common = set(proj_totals.keys()) & set(act_totals.keys())
        season_errors = [abs(proj_totals[pid] - act_totals[pid]) for pid in common]
        season_mae = float(np.mean(season_errors)) if season_errors else 99.0

        rank_corr = {}
        for pos in POSITIONS:
            pos_pids = [pid for pid in common if actual_pos.get(pid) == pos]
            if len(pos_pids) >= 5:
                p = [proj_totals[pid] for pid in pos_pids]
                a = [act_totals[pid] for pid in pos_pids]
                rank_corr[pos] = spearman_rank_correlation(p, a)
            else:
                rank_corr[pos] = 0.0

        boom_threshold = 20.0
        pred_boom, act_boom = {}, {}
        for pid in common:
            pw = proj_by_pw.get(pid, {})
            aw = actual_by_pw.get(pid, {})
            if len(aw) >= 5:
                pred_boom[pid] = sum(1 for v in pw.values() if v >= boom_threshold) / max(len(pw), 1)
                act_boom[pid] = sum(1 for v in aw.values() if v >= boom_threshold) / len(aw)
        cal = boom_bust_calibration(pred_boom, act_boom) if pred_boom else 0.5

        return weekly_mae, season_mae, rank_corr, cal

    a_wm, a_sm, a_rc, a_cal = _compute_arm_metrics(dict(arm_a_proj))
    b_wm, b_sm, b_rc, b_cal = _compute_arm_metrics(dict(arm_b_proj))

    season_metrics = SeasonMetrics(
        test_season=test_season,
        arm_a_rank_corr=a_rc, arm_b_rank_corr=b_rc,
        arm_a_weekly_mae=a_wm, arm_b_weekly_mae=b_wm,
        arm_a_season_mae=a_sm, arm_b_season_mae=b_sm,
        arm_a_calibration=a_cal, arm_b_calibration=b_cal,
    )

    # --- Compute weekly records ---
    records: list[WeeklyPlayerRecord] = []
    common_pids = set(arm_a_proj.keys()) & set(arm_b_proj.keys())
    for pid in common_pids:
        pos = actual_pos.get(pid, arm_b_meta.get(pid, {}).get("position", ""))
        if pos not in positions:
            continue
        name = str(actual_name.get(pid) or arm_b_meta.get(pid, {}).get("name", "") or "")
        team = str(actual_team.get(pid) or arm_b_meta.get(pid, {}).get("team", "") or "")
        common_weeks = set(arm_a_proj[pid].keys()) & set(arm_b_proj[pid].keys())
        for wk in common_weeks:
            if pid not in actual_by_pw or wk not in actual_by_pw[pid]:
                continue
            # Look up matchup/coverage aux (populated by dual-arm builds only)
            maux = matchup_data.get((team, wk), {})
            mctx = maux.get("matchup_ctx")
            mfactors = _filter_matchup_factors(pos, mctx) if mctx else {}
            cov_map = maux.get("coverage", {})
            cov_mods = cov_map.get(pid) if pos == "WR" else None
            records.append(WeeklyPlayerRecord(
                player_id=pid, name=name, position=pos, team=team,
                week=wk, season=test_season,
                projected_fpts_on=arm_b_proj[pid][wk],
                projected_fpts_off=arm_a_proj[pid][wk],
                actual_fpts=actual_by_pw[pid][wk],
                matchup_factors=mfactors,
                coverage_modifiers=cov_mods,
            ))
    weekly_records = records

    return {
        "season_metrics": season_metrics,
        "weekly_records": weekly_records,
        "arm_a_projections": dict(arm_a_proj) if cached_arm_a is None else None,
        "arm_a_meta": arm_a_meta if cached_arm_a is None else None,
    }


def print_header(
    args,
    cache_status: dict[int, bool],
    *,
    comparison_mode: str | None = None,
    seed_mode: str | None = None,
    coverage_summary: Mapping[str, SignalCoverage] | None = None,
) -> None:
    overrides_str = " + [" + ", ".join(args.overrides) + "]" if args.overrides else ""
    cache_hits = [s for s, hit in cache_status.items() if hit]
    cache_misses = [s for s, hit in cache_status.items() if not hit]
    cache_str = ""
    if args.baseline == "bare" and not args.no_cache:
        parts = []
        if cache_hits:
            parts.append(f"HIT ({', '.join(str(s) for s in cache_hits)})")
        if cache_misses:
            parts.append(f"MISS ({', '.join(str(s) for s in cache_misses)})")
        cache_str = ", ".join(parts)

    print("=" * 68)
    print("  A/B VALIDATION")
    print("=" * 68)
    print(f"  baseline    : {args.baseline}")
    print(f"  arm B       : defaults{overrides_str}")
    print(f"  sims        : {args.sims}")
    print(f"  seasons     : {args.seasons}")
    print(f"  scoring     : {args.scoring}")
    if comparison_mode is not None:
        print(f"  comparison  : {comparison_mode}")
    if seed_mode is not None:
        print(f"  seed mode   : {seed_mode}")
    coverage_line = _format_coverage_line(coverage_summary or {})
    if coverage_line:
        print(coverage_line)
    coverage_notes_line = _format_coverage_notes_line(coverage_summary or {})
    if coverage_notes_line:
        print(coverage_notes_line)
    if cache_str:
        print(f"  bare cache  : {cache_str}")
    print("=" * 68)


def print_season_results(season_results: list[SeasonMetrics]) -> None:
    print("\n" + "=" * 68)
    print("  SEASON-LEVEL RESULTS")
    print("=" * 68)

    for sm in season_results:
        print(f"\n  Season {sm.test_season}:")
        rc_parts = []
        for pos in POSITIONS:
            a_val = sm.arm_a_rank_corr.get(pos, 0.0)
            b_val = sm.arm_b_rank_corr.get(pos, 0.0)
            delta = b_val - a_val
            rc_parts.append(f"{pos} {a_val:.3f}->{b_val:.3f} ({delta:+.3f})")
        print(f"    rank_corr:  {rc_parts[0]}  {rc_parts[1]}")
        print(f"                {rc_parts[2]}  {rc_parts[3]}")
        wm_delta = sm.weekly_mae_delta
        sm_delta = sm.season_mae_delta
        print(f"    weekly_mae: {sm.arm_a_weekly_mae:.2f} -> {sm.arm_b_weekly_mae:.2f} ({wm_delta:+.2f})")
        print(f"    season_mae: {sm.arm_a_season_mae:.2f} -> {sm.arm_b_season_mae:.2f} ({sm_delta:+.2f})")

    if len(season_results) > 1:
        avg_rc = sum(r.rank_corr_delta for r in season_results) / len(season_results)
        avg_wm = sum(r.weekly_mae_delta for r in season_results) / len(season_results)
        avg_sm = sum(r.season_mae_delta for r in season_results) / len(season_results)
        print("\n  AVERAGES:")
        print(f"    rank_corr delta:  {avg_rc:+.4f}")
        print(f"    weekly_mae delta: {avg_wm:+.3f}")
        print(f"    season_mae delta: {avg_sm:+.3f}")


def print_market_history_results(
    season_results: list[SeasonMetrics],
    coverage_summary: Mapping[str, SignalCoverage] | None,
) -> None:
    signal = (coverage_summary or {}).get("market_history")
    if signal is None or not signal.enabled:
        return

    covered = signal.covered_seasons
    uncovered = signal.missing_seasons

    print("\n" + "=" * 68)
    print("  MARKET HISTORY COVERED-SEASON READOUT")
    print("=" * 68)
    print(
        f"  covered seasons   : {', '.join(str(season) for season in covered) or '(none)'}"
    )
    print(
        f"  uncovered seasons : {', '.join(str(season) for season in uncovered) or '(none)'}"
    )
    print("  promotion scope   : covered_only")

    covered_results = [
        season_result
        for season_result in season_results
        if season_result.test_season in covered
    ]
    if not covered_results:
        print("  no covered seasons; market-specific averages skipped")
        return

    avg_rc = sum(r.rank_corr_delta for r in covered_results) / len(covered_results)
    avg_wm = sum(r.weekly_mae_delta for r in covered_results) / len(covered_results)
    avg_sm = sum(r.season_mae_delta for r in covered_results) / len(covered_results)
    print(f"  rank_corr delta:  {avg_rc:+.4f}")
    print(f"  weekly_mae delta: {avg_wm:+.3f}")
    print(f"  season_mae delta: {avg_sm:+.3f}")


def print_weekly_results(
    all_records: list[WeeklyPlayerRecord],
    positions: list[str],
    seasons: list[int],
    scoring_config: dict,
) -> tuple[list[WeeklyPositionSummary], DirectionalAccuracyResult | None]:
    """Print weekly metrics and return summaries + directional accuracy."""
    print("\n" + "=" * 68)
    print("  WEEKLY RESULTS")
    print("=" * 68)

    summaries: list[WeeklyPositionSummary] = []
    for pos in positions:
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
            weekly_rank_corr_on=rc_on, weekly_rank_corr_off=rc_off,
            weekly_mae_on=mae_on, weekly_mae_off=mae_off,
            mae_by_tercile=tercile,
            n_player_weeks=len(pos_records), n_weeks=n_weeks,
        )
        summaries.append(summary)

        rc_delta = rc_on - rc_off
        mae_delta = mae_on - mae_off
        print(f"\n  {pos}  ({len(pos_records)} player-weeks, {n_weeks} weeks)")
        print(f"    rank_corr: {rc_off:.4f} -> {rc_on:.4f} ({rc_delta:+.4f})")
        print(f"    weekly_mae: {mae_off:.3f} -> {mae_on:.3f} ({mae_delta:+.3f})")
        if tercile:
            print(f"    mae_by_difficulty: strong={tercile.get('strong', 0):.3f}  "
                  f"neutral={tercile.get('neutral', 0):.3f}  "
                  f"weak={tercile.get('weak', 0):.3f}")

    dir_accuracy: DirectionalAccuracyResult | None = None
    if "WR" in positions:
        loader = DataLoader()
        actuals_by_player: dict[str, list] = defaultdict(list)
        for season in seasons:
            ps = loader.load_player_stats([season])
            season_actuals = load_actual_scores(ps, scoring_config, season)
            for a in season_actuals:
                actuals_by_player[a.player_id].append(a)
        dir_accuracy = compute_directional_accuracy(all_records, actuals_by_player)
        print(f"\n  WR Directional Accuracy: {dir_accuracy.correct_direction}/{dir_accuracy.total_eligible} "
              f"= {dir_accuracy.accuracy:.1%}")

    return summaries, dir_accuracy


def main() -> int:
    parser = build_cli()
    args = parser.parse_args()

    if args.show_ledger:
        entries = load_ledger()
        print(format_ledger_table(entries))
        return 0

    # Hold-out gate
    if any(s >= _HOLDOUT_SEASON for s in args.seasons):
        print(
            f"ERROR: Season {_HOLDOUT_SEASON}+ is reserved as hold-out. "
            "Use --seasons 2022 2023 2024.",
            file=sys.stderr,
        )
        return 1

    # Resolve configs
    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)
    comparison_mode = _comparison_mode(args.baseline)

    if args.baseline == "bare":
        arm_a_configs = build_bare_engine_configs()
        arm_a_ensemble_config = None
    else:
        arm_a_configs = build_engine_configs(defaults)
        arm_a_ensemble_config = load_ensemble_config(defaults)
        if not (
            arm_a_ensemble_config.enabled
            and arm_a_ensemble_config.ff_opportunity.enabled
        ):
            arm_a_ensemble_config = None

    if args.overrides:
        arm_b_dict = apply_overrides(defaults, args.overrides)
    else:
        arm_b_dict = defaults
    arm_b_configs = build_engine_configs(arm_b_dict)
    arm_b_ensemble_config = load_ensemble_config(arm_b_dict)
    if not (
        arm_b_ensemble_config.enabled
        and arm_b_ensemble_config.ff_opportunity.enabled
    ):
        arm_b_ensemble_config = None
    coverage_summary = collect_signal_coverage(arm_b_dict, args.seasons)

    # Check cache
    cache_status: dict[int, bool] = {}
    cached_results: dict[int, dict | None] = {}
    for season in args.seasons:
        if args.baseline == "bare" and not args.no_cache:
            cp = cache_path(season, args.sims, args.scoring, args.training_years)
            cached = load_cache(cp)
            cache_status[season] = cached is not None
            cached_results[season] = cached
        else:
            cache_status[season] = False
            cached_results[season] = None

    print_header(
        args,
        cache_status,
        comparison_mode=comparison_mode,
        seed_mode=SEED_MODE,
        coverage_summary=coverage_summary,
    )

    # Compute workers
    num_seasons = len(args.seasons)
    if args.workers == 1:
        per_season_workers = 1
    elif args.workers > 1:
        per_season_workers = args.workers
    else:
        per_season_workers = default_max_workers(batch_size=288, num_concurrent=num_seasons)
    print(f"  workers     : {per_season_workers} per season")

    # Run seasons
    total_start = time.time()
    all_season_metrics: list[SeasonMetrics] = []
    all_weekly_records: list[WeeklyPlayerRecord] = []
    cache_to_save: list[tuple[int, dict, dict]] = []  # (season, projections, meta)

    if len(args.seasons) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        print(f"\nRunning {len(args.seasons)} seasons in parallel...")
        with ProcessPoolExecutor(max_workers=len(args.seasons)) as pool:
            futures = {
                pool.submit(
                    run_season,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    arm_a_configs=arm_a_configs,
                    arm_b_configs=arm_b_configs,
                    arm_a_ensemble_config=arm_a_ensemble_config,
                    arm_b_ensemble_config=arm_b_ensemble_config,
                    positions=args.positions,
                    max_workers=per_season_workers,
                    cached_arm_a=cached_results[season],
                ): season
                for season in args.seasons
            }
            for future in as_completed(futures):
                season = futures[future]
                result = future.result()
                all_season_metrics.append(result["season_metrics"])
                if result["weekly_records"]:
                    all_weekly_records.extend(result["weekly_records"])
                if result["arm_a_projections"] is not None:
                    cache_to_save.append((
                        season, result["arm_a_projections"], result["arm_a_meta"],
                    ))
                print(f"  Season {season} complete.")
    else:
        for season in args.seasons:
            result = run_season(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                arm_a_configs=arm_a_configs,
                arm_b_configs=arm_b_configs,
                arm_a_ensemble_config=arm_a_ensemble_config,
                arm_b_ensemble_config=arm_b_ensemble_config,
                positions=args.positions,
                max_workers=per_season_workers,
                cached_arm_a=cached_results[season],
            )
            all_season_metrics.append(result["season_metrics"])
            if result["weekly_records"]:
                all_weekly_records.extend(result["weekly_records"])
            if result["arm_a_projections"] is not None:
                cache_to_save.append((
                    season, result["arm_a_projections"], result["arm_a_meta"],
                ))

    # Sort season results
    all_season_metrics.sort(key=lambda sm: sm.test_season)

    total_elapsed = time.time() - total_start
    print(f"\nTotal time: {total_elapsed:.1f}s")

    # Print results
    print_season_results(all_season_metrics)
    print_market_history_results(all_season_metrics, coverage_summary)

    weekly_summaries: list[WeeklyPositionSummary] | None = None
    dir_accuracy: DirectionalAccuracyResult | None = None
    if all_weekly_records:
        weekly_summaries, dir_accuracy = print_weekly_results(
            all_weekly_records, args.positions, args.seasons, scoring_config,
        )

    print("\n" + "=" * 68)

    # Save cache
    if args.baseline == "bare" and not args.no_cache:
        for season, proj, meta in cache_to_save:
            cp = cache_path(season, args.sims, args.scoring, args.training_years)
            save_cache(cp, proj, meta)
            print(f"  Cached bare baseline for {season}")

    # Save to ledger
    if args.label:
        market_history_signal = (coverage_summary or {}).get("market_history")
        entry = LedgerEntry(
            schema_version=CURRENT_LEDGER_SCHEMA_VERSION,
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            scoring=args.scoring,
            baseline=args.baseline,
            comparison_mode=comparison_mode,
            overrides=args.overrides,
            seed_mode=SEED_MODE,
            promotion_evidence_scope=(
                "covered_only"
                if market_history_signal is not None and market_history_signal.enabled
                else None
            ),
            coverage_summary=coverage_summary,
            config_snapshot=arm_b_dict if args.overrides else defaults,
            season_results=all_season_metrics,
            weekly_summaries=weekly_summaries,
            directional_accuracy=dir_accuracy,
        )
        ledger = load_ledger()
        ledger.append(entry)
        save_ledger(DEFAULT_LEDGER_PATH, ledger)
        print(f"\n  Appended to ledger as #{len(ledger)}: {args.label}")
        print(format_ledger_table(ledger))

    return 0


if __name__ == "__main__":
    sys.exit(main())
