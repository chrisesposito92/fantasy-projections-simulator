"""Tests for the PFF WR/TE depth-role engine."""

from __future__ import annotations

import pytest
import polars as pl

from fantasy_sim.data.pff.depth_role import DepthRoleEngine
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import DepthRoleConfig, DepthRolePositionConfig
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
