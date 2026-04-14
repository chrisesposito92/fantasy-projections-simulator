"""Tests for the PFF WR/TE depth-role engine."""

from __future__ import annotations

import numpy as np
import pytest
import polars as pl

from fantasy_sim.data.pff.depth_role import DepthRoleEngine
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import (
    DepthRoleConfig,
    DepthRoleEfficiencyConfig,
    DepthRoleEfficiencyPositionConfig,
    DepthRolePositionConfig,
)
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster

_SIDE_ROUTE_COLUMNS = (
    "left_behind_los_routes",
    "center_behind_los_routes",
    "right_behind_los_routes",
    "left_short_routes",
    "center_short_routes",
    "right_short_routes",
    "left_medium_routes",
    "center_medium_routes",
    "right_medium_routes",
    "left_deep_routes",
    "center_deep_routes",
    "right_deep_routes",
)


def _make_roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel(
                "WR_A",
                "WR A",
                "WR",
                "KC",
                PlayerUsage(target_share=0.28, air_yards_share=0.34),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "WR_B",
                "WR B",
                "WR",
                "KC",
                PlayerUsage(target_share=0.22, air_yards_share=0.24),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "TE_A",
                "TE A",
                "TE",
                "KC",
                PlayerUsage(target_share=0.18, air_yards_share=0.12),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "RB_A",
                "RB A",
                "RB",
                "KC",
                PlayerUsage(target_share=0.10, air_yards_share=0.04),
                PlayerOutcomes(),
            ),
        ],
    )


def _write_receiving_depth(pff_dir, season: int, rows: list[dict]) -> None:
    pff_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Int64,
        "left_behind_los_routes": pl.Float64,
        "center_behind_los_routes": pl.Float64,
        "right_behind_los_routes": pl.Float64,
        "left_short_routes": pl.Float64,
        "center_short_routes": pl.Float64,
        "right_short_routes": pl.Float64,
        "left_medium_routes": pl.Float64,
        "center_medium_routes": pl.Float64,
        "right_medium_routes": pl.Float64,
        "left_deep_routes": pl.Float64,
        "center_deep_routes": pl.Float64,
        "right_deep_routes": pl.Float64,
        "behind_los_routes": pl.Float64,
        "short_routes": pl.Float64,
        "medium_routes": pl.Float64,
        "deep_routes": pl.Float64,
        "short_targets": pl.Float64,
        "medium_targets": pl.Float64,
        "deep_targets": pl.Float64,
        "behind_los_targets": pl.Float64,
        "short_avg_depth_of_target": pl.Float64,
        "medium_avg_depth_of_target": pl.Float64,
        "deep_avg_depth_of_target": pl.Float64,
        "behind_los_avg_depth_of_target": pl.Float64,
        "behind_los_receptions": pl.Float64,
        "short_receptions": pl.Float64,
        "medium_receptions": pl.Float64,
        "deep_receptions": pl.Float64,
        "behind_los_yards": pl.Float64,
        "short_yards": pl.Float64,
        "medium_yards": pl.Float64,
        "deep_yards": pl.Float64,
    }
    df = pl.DataFrame(rows, schema=schema, infer_schema_length=None) if rows else pl.DataFrame(schema=schema)
    df.write_parquet(pff_dir / f"receiving_depth_{season}.parquet")


def _receiving_depth_row(
    *,
    player_id: int,
    player: str,
    team: str,
    position: str,
    season: int,
    week: int,
    game_id: int,
    side_routes: dict[str, float],
    targets: dict[str, float],
    adots: dict[str, float],
    extras: dict[str, float] | None = None,
) -> dict[str, float | int | str]:
    row: dict[str, float | int | str] = {
        "player_id": player_id,
        "player": player,
        "team": team,
        "position": position,
        "season": season,
        "week": week,
        "game_id": game_id,
    }
    for column in _SIDE_ROUTE_COLUMNS:
        row[column] = 0.0
    row.update(side_routes)

    for bucket in ("behind_los", "short", "medium", "deep"):
        target_value = targets.get(bucket, 0.0)
        # In the production parquet these bucketed route fields track targets/base_targets,
        # not actual route volume. The engine should use side-split route columns instead.
        row[f"{bucket}_routes"] = target_value
        row[f"{bucket}_targets"] = target_value
        row[f"{bucket}_avg_depth_of_target"] = adots.get(bucket, 0.0)
        row[f"{bucket}_receptions"] = 0.0
        row[f"{bucket}_yards"] = 0.0

    if extras is not None:
        row.update(extras)

    return row


def _engine(pff_dir) -> DepthRoleEngine:
    config = DepthRoleConfig(
        enabled=True,
        positions=("WR", "TE"),
        wr=DepthRolePositionConfig(0.10, 0.12, (0.94, 1.06)),
        te=DepthRolePositionConfig(0.08, 0.06, (0.95, 1.05)),
        min_routes=15,
        min_targets=6,
        min_games=4,
        early_season_blend=True,
    )
    return DepthRoleEngine(PffLoader(pff_dir), config)


def _engine_with_config(
    pff_dir,
    *,
    early_season_blend: bool = True,
) -> DepthRoleEngine:
    config = DepthRoleConfig(
        enabled=True,
        positions=("WR", "TE"),
        wr=DepthRolePositionConfig(0.10, 0.12, (0.94, 1.06)),
        te=DepthRolePositionConfig(0.08, 0.06, (0.95, 1.05)),
        min_routes=15,
        min_targets=6,
        min_games=4,
        early_season_blend=early_season_blend,
    )
    return DepthRoleEngine(PffLoader(pff_dir), config)


def _efficiency_enabled_engine(
    pff_dir,
    *,
    early_season_blend: bool = True,
    min_games: int = 4,
    efficiency_min_games: int = 4,
) -> DepthRoleEngine:
    config = DepthRoleConfig(
        enabled=True,
        positions=("WR", "TE"),
        wr=DepthRolePositionConfig(0.10, 0.12, (0.94, 1.06)),
        te=DepthRolePositionConfig(0.08, 0.06, (0.95, 1.05)),
        min_routes=15,
        min_targets=6,
        min_games=min_games,
        early_season_blend=early_season_blend,
        efficiency=DepthRoleEfficiencyConfig(
            enabled=True,
            min_routes=15,
            min_receptions=6,
            min_games=efficiency_min_games,
            catch_rate_clamp=(0.94, 1.06),
            yards_scale_clamp=(0.92, 1.08),
            wr=DepthRoleEfficiencyPositionConfig(0.08, 0.10),
            te=DepthRoleEfficiencyPositionConfig(0.06, 0.08),
        ),
    )
    return DepthRoleEngine(PffLoader(pff_dir), config)


def test_apply_adjusts_wr_and_te_role_volume_only(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "left_short_routes": 6,
                    "center_short_routes": 4,
                    "left_medium_routes": 4,
                    "center_medium_routes": 4,
                    "left_deep_routes": 6,
                    "right_deep_routes": 4,
                },
                targets={"short": 2, "medium": 3, "deep": 5},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 11.0, "deep": 24.0},
            ),
            _receiving_depth_row(
                player_id=102,
                player="WR B",
                team="KC",
                position="RWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "right_behind_los_routes": 2,
                    "right_short_routes": 8,
                    "center_short_routes": 6,
                    "right_medium_routes": 4,
                    "center_medium_routes": 4,
                    "right_deep_routes": 2,
                    "center_deep_routes": 2,
                },
                targets={"short": 4, "medium": 2},
                adots={"behind_los": -1.0, "short": 5.0, "medium": 10.0, "deep": 0.0},
            ),
            _receiving_depth_row(
                player_id=103,
                player="TE A",
                team="KC",
                position="TE-L",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "center_behind_los_routes": 1,
                    "left_behind_los_routes": 2,
                    "center_short_routes": 5,
                    "left_short_routes": 6,
                    "center_medium_routes": 4,
                    "left_medium_routes": 3,
                    "center_deep_routes": 2,
                    "left_deep_routes": 1,
                },
                targets={"short": 5, "medium": 2, "deep": 1},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 8.0, "deep": 18.0},
            ),
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(
        roster,
        pff_crosswalk={101: "WR_A", 102: "WR_B", 103: "TE_A"},
        target_season=2024,
        max_week=18,
    )

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_b = next(player for player in roster.players if player.player_id == "WR_B")
    te_a = next(player for player in roster.players if player.player_id == "TE_A")
    rb_a = next(player for player in roster.players if player.player_id == "RB_A")

    assert wr_a.usage.target_share > 0.28
    assert wr_a.usage.air_yards_share > 0.34
    assert wr_b.usage.air_yards_share < 0.24
    assert te_a.usage.target_share > 0.18
    assert rb_a.usage.target_share == 0.10


def test_apply_clamps_extreme_roles_and_keeps_non_volume_fields_unchanged(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_short_routes": 4,
                    "center_short_routes": 3,
                    "left_medium_routes": 4,
                    "center_medium_routes": 5,
                    "left_deep_routes": 9,
                    "right_deep_routes": 10,
                },
                targets={"deep": 12},
                adots={"behind_los": -1.0, "short": 0.0, "medium": 0.0, "deep": 25.0},
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.61
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    assert wr_a.usage.target_share == pytest.approx(0.28 * 1.06)
    assert wr_a.usage.air_yards_share == pytest.approx(0.34 * 1.06)
    assert wr_a.outcomes.catch_rate == pytest.approx(0.61)


def test_low_sample_players_stay_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_short_routes": 2,
                    "center_short_routes": 1,
                    "left_medium_routes": 2,
                    "left_behind_los_routes": 1,
                },
                targets={"short": 1, "medium": 1},
                adots={"behind_los": -1.0, "short": 5.0, "medium": 11.0, "deep": 0.0},
            ),
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.target_share == 0.28
    assert wr_a.usage.air_yards_share == 0.34


def test_early_season_blend_uses_previous_season_when_current_sample_is_thin(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2023,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2023,
                week=10,
                game_id=100,
                side_routes={
                    "left_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "left_short_routes": 6,
                    "center_short_routes": 5,
                    "left_medium_routes": 5,
                    "center_medium_routes": 4,
                    "left_deep_routes": 6,
                    "right_deep_routes": 6,
                },
                targets={"short": 2, "medium": 3, "deep": 6},
                adots={"behind_los": -1.0, "short": 5.0, "medium": 11.0, "deep": 23.0},
            )
        ],
    )
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "left_short_routes": 3,
                    "center_short_routes": 3,
                    "left_medium_routes": 1,
                    "center_medium_routes": 1,
                },
                targets={"short": 2},
                adots={"behind_los": -1.0, "short": 3.0, "medium": 0.0, "deep": 0.0},
            )
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 2)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.air_yards_share > 0.34


def test_missing_crosswalk_stays_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "left_short_routes": 6,
                    "center_short_routes": 4,
                    "left_medium_routes": 4,
                    "center_medium_routes": 4,
                    "left_deep_routes": 6,
                    "right_deep_routes": 4,
                },
                targets={"short": 2, "medium": 3, "deep": 5},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 11.0, "deep": 24.0},
            )
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {999: "WR_A"}, 2024, 18)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.target_share == 0.28
    assert wr_a.usage.air_yards_share == 0.34


def test_partial_crosswalk_team_denominator_stays_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "left_short_routes": 6,
                    "center_short_routes": 4,
                    "left_medium_routes": 4,
                    "center_medium_routes": 4,
                    "left_deep_routes": 6,
                    "right_deep_routes": 4,
                },
                targets={"short": 2, "medium": 3, "deep": 5},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 11.0, "deep": 24.0},
            ),
            _receiving_depth_row(
                player_id=102,
                player="WR B",
                team="KC",
                position="RWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "right_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "right_short_routes": 7,
                    "center_short_routes": 6,
                    "right_medium_routes": 5,
                    "center_medium_routes": 5,
                    "right_deep_routes": 4,
                    "center_deep_routes": 3,
                },
                targets={"short": 3, "medium": 4, "deep": 3},
                adots={"behind_los": -1.0, "short": 5.0, "medium": 11.0, "deep": 18.0},
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.58
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    assert wr_a.usage.target_share == pytest.approx(0.28)
    assert wr_a.usage.air_yards_share == pytest.approx(0.34)
    assert wr_a.outcomes.catch_rate == pytest.approx(0.58)


def test_disabled_blend_does_not_fallback_to_previous_season_only(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2023,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2023,
                week=10,
                game_id=100,
                side_routes={
                    "left_behind_los_routes": 1,
                    "center_behind_los_routes": 1,
                    "left_short_routes": 6,
                    "center_short_routes": 5,
                    "left_medium_routes": 5,
                    "center_medium_routes": 4,
                    "left_deep_routes": 6,
                    "right_deep_routes": 6,
                },
                targets={"short": 2, "medium": 3, "deep": 6},
                adots={"behind_los": -1.0, "short": 5.0, "medium": 11.0, "deep": 23.0},
            )
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.64
    engine = _engine_with_config(pff_dir, early_season_blend=False)

    engine.apply(roster, {101: "WR_A"}, 2024, 2)

    assert wr_a.usage.target_share == pytest.approx(0.28)
    assert wr_a.usage.air_yards_share == pytest.approx(0.34)
    assert wr_a.outcomes.catch_rate == pytest.approx(0.64)


def test_efficiency_apply_isolated_from_volume_and_preserves_rz_yards_dist(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_short_routes": 8,
                    "center_short_routes": 4,
                    "left_medium_routes": 5,
                    "center_medium_routes": 3,
                    "left_deep_routes": 4,
                    "right_deep_routes": 4,
                },
                targets={"short": 4, "medium": 3, "deep": 3},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 11.0, "deep": 20.0},
                extras={
                    "short_receptions": 4,
                    "medium_receptions": 3,
                    "deep_receptions": 2,
                    "short_yards": 32,
                    "medium_yards": 39,
                    "deep_yards": 46,
                },
            ),
            _receiving_depth_row(
                player_id=103,
                player="TE A",
                team="KC",
                position="TE-L",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "center_short_routes": 7,
                    "left_short_routes": 5,
                    "center_medium_routes": 4,
                    "left_medium_routes": 2,
                    "center_deep_routes": 1,
                },
                targets={"short": 5, "medium": 2, "deep": 1},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 8.0, "deep": 16.0},
                extras={
                    "short_receptions": 5,
                    "medium_receptions": 2,
                    "deep_receptions": 1,
                    "short_yards": 30,
                    "medium_yards": 18,
                    "deep_yards": 16,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    te_a = next(player for player in roster.players if player.player_id == "TE_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])
    wr_a.outcomes.rz_receiving_yards_dist = np.array([5.0, 7.0, 9.0])
    te_a.outcomes.catch_rate = 0.68
    te_a.outcomes.red_zone_catch_rate = 0.62
    te_a.outcomes.receiving_yards_dist = np.array([6.0, 8.0, 10.0])
    te_a.outcomes.rz_receiving_yards_dist = np.array([4.0, 5.0, 6.0])

    original_wr_target_share = wr_a.usage.target_share
    original_wr_air_share = wr_a.usage.air_yards_share
    original_te_target_share = te_a.usage.target_share
    original_te_air_share = te_a.usage.air_yards_share
    original_wr_rz_yards = wr_a.outcomes.rz_receiving_yards_dist.copy()
    original_te_rz_yards = te_a.outcomes.rz_receiving_yards_dist.copy()

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(
        roster,
        pff_crosswalk={101: "WR_A", 103: "TE_A"},
        target_season=2024,
        max_week=18,
    )

    assert wr_a.usage.target_share == original_wr_target_share
    assert wr_a.usage.air_yards_share == original_wr_air_share
    assert te_a.usage.target_share == original_te_target_share
    assert te_a.usage.air_yards_share == original_te_air_share
    assert np.array_equal(wr_a.outcomes.rz_receiving_yards_dist, original_wr_rz_yards)
    assert np.array_equal(te_a.outcomes.rz_receiving_yards_dist, original_te_rz_yards)
    assert wr_a.outcomes.catch_rate == pytest.approx(0.624)
    assert wr_a.outcomes.red_zone_catch_rate == pytest.approx(0.5616)
    assert np.array_equal(
        wr_a.outcomes.receiving_yards_dist,
        np.array([8.24, 10.3, 12.36]),
    )
    assert te_a.outcomes.catch_rate == pytest.approx(0.6992)


def test_efficiency_scales_red_zone_catch_rate_using_final_clipped_catch_ratio(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"left_short_routes": 8, "left_medium_routes": 6, "left_deep_routes": 6},
                targets={"short": 4, "medium": 3, "deep": 3},
                adots={"short": 4.0, "medium": 11.0, "deep": 20.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 4,
                    "medium_receptions": 3,
                    "deep_receptions": 2,
                    "short_yards": 32,
                    "medium_yards": 39,
                    "deep_yards": 46,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 1.20
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    catch_ratio = wr_a.outcomes.catch_rate / 1.20
    assert wr_a.outcomes.catch_rate == pytest.approx(1.0)
    assert wr_a.outcomes.red_zone_catch_rate == pytest.approx(0.54 * catch_ratio)


def test_efficiency_stays_neutral_when_reception_sample_is_thin(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"left_short_routes": 8, "left_medium_routes": 6, "left_deep_routes": 6},
                targets={"short": 3, "medium": 2, "deep": 1},
                adots={"short": 4.0, "medium": 11.0, "deep": 20.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 2,
                    "medium_receptions": 1,
                    "deep_receptions": 0,
                    "short_yards": 14,
                    "medium_yards": 9,
                    "deep_yards": 0,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])
    original_dist = wr_a.outcomes.receiving_yards_dist.copy()

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    assert wr_a.outcomes.catch_rate == 0.60
    assert wr_a.outcomes.red_zone_catch_rate == 0.54
    assert np.array_equal(wr_a.outcomes.receiving_yards_dist, original_dist)


def test_efficiency_clamps_catch_rate_and_yards_scale(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"left_short_routes": 10, "left_medium_routes": 8, "left_deep_routes": 8},
                targets={"short": 5, "medium": 4, "deep": 3},
                adots={"short": 4.0, "medium": 12.0, "deep": 25.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 5,
                    "medium_receptions": 4,
                    "deep_receptions": 3,
                    "short_yards": 100,
                    "medium_yards": 120,
                    "deep_yards": 120,
                },
            ),
            _receiving_depth_row(
                player_id=103,
                player="TE A",
                team="KC",
                position="TE-L",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"center_short_routes": 10, "center_medium_routes": 8, "center_deep_routes": 8},
                targets={"short": 5, "medium": 4, "deep": 3},
                adots={"short": 3.0, "medium": 7.0, "deep": 10.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 1,
                    "medium_receptions": 1,
                    "deep_receptions": 0,
                    "short_yards": 5,
                    "medium_yards": 5,
                    "deep_yards": 0,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(roster, {101: "WR_A", 103: "TE_A"}, 2024, 18)

    assert wr_a.outcomes.catch_rate <= 0.60 * 1.06 + 1e-9
    assert wr_a.outcomes.receiving_yards_dist.mean() <= (
        np.array([8.0, 10.0, 12.0]).mean() * 1.08 + 1e-9
    )


def test_efficiency_uses_its_own_min_games_threshold(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2023,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2023,
                week=10,
                game_id=100,
                side_routes={
                    "left_short_routes": 8,
                    "left_medium_routes": 6,
                    "left_deep_routes": 6,
                },
                targets={"short": 4, "medium": 2, "deep": 2},
                adots={"short": 4.0, "medium": 10.0, "deep": 18.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 3,
                    "medium_receptions": 2,
                    "deep_receptions": 1,
                    "short_yards": 15,
                    "medium_yards": 10,
                    "deep_yards": 5,
                },
            )
        ],
    )
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_short_routes": 8,
                    "left_medium_routes": 6,
                    "left_deep_routes": 6,
                },
                targets={"short": 4, "medium": 2, "deep": 2},
                adots={"short": 4.0, "medium": 11.0, "deep": 20.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 4,
                    "medium_receptions": 2,
                    "deep_receptions": 2,
                    "short_yards": 32,
                    "medium_yards": 20,
                    "deep_yards": 28,
                },
            )
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])

    engine = _efficiency_enabled_engine(
        pff_dir,
        early_season_blend=True,
        min_games=99,
        efficiency_min_games=1,
    )
    engine.apply(roster, {101: "WR_A"}, 2024, 2)

    assert wr_a.outcomes.catch_rate == pytest.approx(0.632)
    assert wr_a.outcomes.red_zone_catch_rate == pytest.approx(0.5688)
