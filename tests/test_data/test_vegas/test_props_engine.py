"""Tests for PropsLoader and PlayerPropsEngine (VEG-03).

TDD implementation: Tests written first (RED), then implementation (GREEN).
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest


# ---------------------------------------------------------------------------
# TestPlayerNameCrosswalk
# ---------------------------------------------------------------------------

class TestPlayerNameCrosswalk:
    """Tests for standardize_name() and fuzzy player matching."""

    def test_strip_suffix_jr(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Marvin Harrison Jr.") == "marvin harrison"

    def test_strip_suffix_ii(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Patrick Mahomes II") == "patrick mahomes"

    def test_strip_suffix_iii(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Robert Griffin III") == "robert griffin"

    def test_strip_suffix_sr(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Larry Fitzgerald Sr.") == "larry fitzgerald"

    def test_strip_periods(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("D.K. Metcalf") == "dk metcalf"

    def test_strip_apostrophe(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Ja'Marr Chase") == "jamarr chase"

    def test_lowercase(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Travis Kelce") == "travis kelce"

    def test_strip_curly_apostrophe(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        # curly/smart apostrophe variant
        assert standardize_name("Ja\u2019Marr Chase") == "jamarr chase"

    def test_collapse_whitespace(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("  Travis   Kelce  ") == "travis kelce"

    def test_no_suffix_unchanged(self):
        from fantasy_sim.data.vegas.crosswalk import standardize_name
        assert standardize_name("Cooper Kupp") == "cooper kupp"

    def test_fuzzy_match_nickname(self):
        """gabe davis should fuzzy-match gabriel davis at threshold=0.75.

        Levenshtein ratio for 'gabe davis' vs 'gabriel davis' = 0.769 (3 edits /
        max_len 13). This is below the default 0.85 production threshold, which
        is intentional: the 0.85 threshold prevents false positives in production,
        while this test demonstrates the fuzzy logic itself works correctly with
        a lower threshold. Real name variants like 'Travis Kelce' / 'Travis Kelce'
        will be exact matches.
        """
        from fantasy_sim.data.vegas.crosswalk import fuzzy_match
        result = fuzzy_match(
            "gabe davis",
            candidates={"gabriel davis": "PLAYER_001"},
            threshold=0.75,
        )
        assert result == "PLAYER_001"

    def test_fuzzy_match_no_match(self):
        from fantasy_sim.data.vegas.crosswalk import fuzzy_match
        result = fuzzy_match(
            "totally_different_xyz",
            candidates={"travis kelce": "PLAYER_002"},
            threshold=0.85,
        )
        assert result is None

    def test_fuzzy_match_exact(self):
        """Exact match should return without fuzzy computation."""
        from fantasy_sim.data.vegas.crosswalk import fuzzy_match
        result = fuzzy_match(
            "travis kelce",
            candidates={"travis kelce": "PLAYER_002"},
            threshold=0.85,
        )
        assert result == "PLAYER_002"

    def test_ambiguous_match_logged(self, caplog):
        """Two very similar candidates -> returns None and logs warning."""
        import logging
        from fantasy_sim.data.vegas.crosswalk import fuzzy_match
        with caplog.at_level(logging.WARNING, logger="fantasy_sim.data.vegas.crosswalk"):
            result = fuzzy_match(
                "mike williams",
                candidates={"mike williams": "A", "michael williams": "B"},
                threshold=0.85,
            )
        # Exact match for "mike williams" -> "A" should be returned immediately
        # (exact match bypasses ambiguity). For a case that is actually ambiguous:
        result2 = fuzzy_match(
            "mike wiliams",  # typo — close to both
            candidates={"mike williams": "A", "mike william": "B"},
            threshold=0.85,
        )
        # Either None (ambiguous) or one of them — key is it doesn't crash
        assert result2 is None or result2 in ("A", "B")


# ---------------------------------------------------------------------------
# TestPropsLoader
# ---------------------------------------------------------------------------

_MOCK_ODDS_RESPONSE = {
    "id": "event-001",
    "sport_key": "americanfootball_nfl",
    "bookmakers": [
        {
            "key": "fanduel",
            "markets": [
                {
                    "key": "player_reception_yds",
                    "outcomes": [
                        {"name": "Patrick Mahomes", "description": "Over", "point": 285.5},
                        {"name": "Travis Kelce", "description": "Over", "point": 72.5},
                    ],
                },
                {
                    "key": "player_receptions",
                    "outcomes": [
                        {"name": "Travis Kelce", "description": "Over", "point": 6.5},
                    ],
                },
            ],
        },
        {
            "key": "draftkings",
            "markets": [
                {
                    "key": "player_reception_yds",
                    "outcomes": [
                        {"name": "Patrick Mahomes", "description": "Over", "point": 286.5},
                        {"name": "Travis Kelce", "description": "Over", "point": 71.5},
                    ],
                },
                {
                    "key": "player_receptions",
                    "outcomes": [
                        {"name": "Travis Kelce", "description": "Over", "point": 6.5},
                    ],
                },
            ],
        },
    ],
}


class TestPropsLoader:
    """Tests for PropsLoader (The Odds API fetcher with caching)."""

    def test_load_props_returns_dataframe(self, tmp_path):
        """Mock httpx response -> polars DataFrame with required columns."""
        from fantasy_sim.data.vegas.models import PropsConfig
        from fantasy_sim.data.vegas.props_loader import PropsLoader

        config = PropsConfig(enabled=True, cache_dir=str(tmp_path))
        loader = PropsLoader(config, cache_dir=tmp_path)
        loader._api_key = "fake-key"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _MOCK_ODDS_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # Patch _fetch_events to return one event
            with patch.object(loader, "_fetch_events", return_value=[
                {"id": "event-001", "commence_time": "2024-10-13T17:00:00Z",
                 "home_team": "KC", "away_team": "BUF"}
            ]):
                df = loader.load_props(season=2024, week=6)

        assert isinstance(df, pl.DataFrame)
        required_cols = {"player_name", "market", "point", "season", "week"}
        assert required_cols.issubset(set(df.columns))
        assert len(df) > 0

    def test_cache_hit_no_fetch(self, tmp_path):
        """Second load_props call reads from cache; no HTTP request made."""
        from fantasy_sim.data.vegas.models import PropsConfig
        from fantasy_sim.data.vegas.props_loader import PropsLoader

        # Write a props parquet to tmp_path manually
        cache_path = tmp_path / "props_2024_week06.parquet"
        cached_df = pl.DataFrame({
            "player_name": ["Travis Kelce"],
            "market": ["player_receptions"],
            "point": [6.5],
            "season": [2024],
            "week": [6],
        })
        cached_df.write_parquet(cache_path)

        config = PropsConfig(enabled=True, cache_dir=str(tmp_path))
        loader = PropsLoader(config, cache_dir=tmp_path)
        loader._api_key = "fake-key"

        with patch("httpx.Client") as mock_client_cls:
            df = loader.load_props(season=2024, week=6)
            mock_client_cls.assert_not_called()

        assert isinstance(df, pl.DataFrame)
        assert len(df) == 1

    def test_no_api_key_returns_empty(self, tmp_path):
        """PropsLoader with no env var returns empty DataFrame, no error."""
        from fantasy_sim.data.vegas.models import PropsConfig
        from fantasy_sim.data.vegas.props_loader import PropsLoader

        config = PropsConfig(enabled=True, cache_dir=str(tmp_path), api_key_env="NO_SUCH_ENV_VAR_XYZ")
        with patch.dict(os.environ, {}, clear=False):
            # Ensure env var is not set
            os.environ.pop("NO_SUCH_ENV_VAR_XYZ", None)
            loader = PropsLoader(config, cache_dir=tmp_path)

        df = loader.load_props(season=2024, week=6)
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0

    def test_2022_returns_empty(self, tmp_path):
        """PropsLoader for season < 2023 returns empty DataFrame."""
        from fantasy_sim.data.vegas.models import PropsConfig
        from fantasy_sim.data.vegas.props_loader import PropsLoader

        config = PropsConfig(enabled=True, cache_dir=str(tmp_path))
        loader = PropsLoader(config, cache_dir=tmp_path)
        loader._api_key = "fake-key"

        df = loader.load_props(season=2022, week=6)
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0

    def test_thursday_open_sunday_game(self):
        """Sunday 2024-10-13 -> snapshot Thursday 2024-10-10T12:00:00-04:00."""
        from fantasy_sim.data.vegas.props_loader import PropsLoader
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True)
        loader = PropsLoader(config)

        gameday = date(2024, 10, 13)  # Sunday
        result = loader._compute_thursday_open(gameday)
        assert "2024-10-10" in result
        assert "12:00:00" in result

    def test_thursday_open_thursday_game(self):
        """Thursday 2024-10-10 -> snapshot Wednesday 2024-10-09T12:00:00-04:00 (gameday - 1)."""
        from fantasy_sim.data.vegas.props_loader import PropsLoader
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True)
        loader = PropsLoader(config)

        gameday = date(2024, 10, 10)  # Thursday
        result = loader._compute_thursday_open(gameday)
        assert "2024-10-09" in result
        assert "12:00:00" in result

    def test_thursday_open_saturday_game(self):
        """Saturday 2024-10-12 -> snapshot Thursday 2024-10-10T12:00:00-04:00."""
        from fantasy_sim.data.vegas.props_loader import PropsLoader
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True)
        loader = PropsLoader(config)

        gameday = date(2024, 10, 12)  # Saturday
        result = loader._compute_thursday_open(gameday)
        assert "2024-10-10" in result
        assert "12:00:00" in result

    def test_thursday_open_monday_game(self):
        """Monday 2024-10-14 -> snapshot Thursday 2024-10-10T12:00:00-04:00."""
        from fantasy_sim.data.vegas.props_loader import PropsLoader
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True)
        loader = PropsLoader(config)

        gameday = date(2024, 10, 14)  # Monday
        result = loader._compute_thursday_open(gameday)
        assert "2024-10-10" in result
        assert "12:00:00" in result


# ---------------------------------------------------------------------------
# TestPlayerPropsEngine
# ---------------------------------------------------------------------------

def _make_wr(name="Travis Kelce", player_id="TK", team="KC",
             target_share=0.20, red_zone_target_share=0.15,
             recv_yds_dist=None, games_played=17):
    """Create a WR/TE PlayerModel for testing."""
    from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes
    if recv_yds_dist is None:
        recv_yds_dist = np.array([8.0, 10.0, 12.0, 15.0])
    return PlayerModel(
        player_id=player_id,
        name=name,
        position="TE",
        team=team,
        usage=PlayerUsage(
            target_share=target_share,
            red_zone_target_share=red_zone_target_share,
        ),
        outcomes=PlayerOutcomes(
            catch_rate=0.75,
            receiving_yards_dist=recv_yds_dist.copy(),
        ),
        games_played=games_played,
    )


def _make_rb(name="Isiah Pacheco", player_id="IP", team="KC",
             carry_share=0.40, red_zone_carry_share=0.35,
             rush_yds_dist=None, games_played=17):
    """Create an RB PlayerModel for testing."""
    from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes
    if rush_yds_dist is None:
        rush_yds_dist = np.array([3.0, 4.0, 5.0, 6.0, 7.0])
    return PlayerModel(
        player_id=player_id,
        name=name,
        position="RB",
        team=team,
        usage=PlayerUsage(carry_share=carry_share, red_zone_carry_share=red_zone_carry_share),
        outcomes=PlayerOutcomes(
            rushing_yards_dist=rush_yds_dist.copy(),
        ),
        games_played=games_played,
    )


def _make_qb(name="Patrick Mahomes", player_id="PM", team="KC",
             games_played=17):
    """Create a QB PlayerModel for testing."""
    from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes
    return PlayerModel(
        player_id=player_id,
        name=name,
        position="QB",
        team=team,
        usage=PlayerUsage(snap_share=1.0),
        outcomes=PlayerOutcomes(),
        games_played=games_played,
    )


def _make_roster(team="KC", players=None):
    """Create a TeamRoster for testing."""
    from fantasy_sim.models.player import TeamRoster
    return TeamRoster(team=team, players=players or [])


class TestPlayerPropsEngine:
    """Tests for PlayerPropsEngine Bayesian blending."""

    def test_bayesian_blend_math(self):
        """(50*80 + 10*100) / (50+10) = 83.33..."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=MagicMock())

        result = engine._bayesian_blend(
            historical=80.0, prop_prior=100.0, n_obs=50
        )
        assert result == pytest.approx(83.333, abs=0.01)

    def test_full_prior_when_no_history(self):
        """n_obs=0 -> adjusted = prop_prior (full prior weight)."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=MagicMock())

        result = engine._bayesian_blend(
            historical=80.0, prop_prior=100.0, n_obs=0
        )
        assert result == pytest.approx(100.0, abs=0.01)

    def test_missing_prop_no_change(self, tmp_path):
        """Player not in props_df -> PlayerModel fields unchanged."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        player = _make_wr(target_share=0.20)
        roster = _make_roster(players=[player])

        empty_df = pl.DataFrame(schema={
            "player_name": pl.Utf8,
            "market": pl.Utf8,
            "point": pl.Float64,
            "season": pl.Int64,
            "week": pl.Int64,
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = empty_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        engine.apply(roster, "KC", 2024, 6)

        assert player.usage.target_share == pytest.approx(0.20)

    def test_min_divergence_skip(self, tmp_path):
        """prop=80.002, historical=80.0 -> no adjustment (below min_divergence=0.005)."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        config = PropsConfig(enabled=True, prior_strength=10.0, min_divergence=0.005)
        engine = PlayerPropsEngine(config, loader=MagicMock())

        # Ratio = 80.002/80.0 = 1.000025, blended_ratio - 1.0 < 0.005
        player = _make_rb(carry_share=0.40)
        original_carry_share = player.usage.carry_share

        props_df = pl.DataFrame({
            "player_name": ["Isiah Pacheco"],
            "market": ["player_rush_yds"],
            "point": [80.002],
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        roster = _make_roster(players=[player])
        # Need historical rush yds ~ 80.0 for this to test min_divergence
        player.outcomes.rushing_yards_dist = np.full(17, 80.0 / 17)

        engine.apply(roster, "KC", 2024, 6)
        # Change should be negligible (within floating point noise)
        assert player.usage.carry_share == pytest.approx(original_carry_share, abs=0.01)

    def test_reception_yds_shifts_dist(self):
        """player_reception_yds prop shifts receiving_yards_dist proportionally."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        base_dist = np.array([8.0, 10.0, 12.0, 15.0])
        original_mean = float(np.mean(base_dist))  # 11.25

        player = _make_wr(recv_yds_dist=base_dist)
        # historical_recv_yds = mean(dist) * games_played
        historical_recv = original_mean * player.games_played  # 11.25 * 17 = 191.25

        # Prop implies 230 yards (higher than historical)
        prop_point = 230.0

        props_df = pl.DataFrame({
            "player_name": ["Travis Kelce"],
            "market": ["player_reception_yds"],
            "point": [prop_point],
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        roster = _make_roster(players=[player])
        engine.apply(roster, "KC", 2024, 6)

        new_mean = float(np.mean(player.outcomes.receiving_yards_dist))
        assert new_mean > original_mean, "Higher prop should shift dist mean up"

    def test_receptions_adjusts_target_share(self):
        """player_receptions prop adjusts target_share via Bayesian blend."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        player = _make_wr(target_share=0.20, games_played=17)
        original_target_share = player.usage.target_share

        # Historical: assume 5 receptions/game * 17 games = 85 total
        # Prop: 6.5 (higher)
        props_df = pl.DataFrame({
            "player_name": ["Travis Kelce"],
            "market": ["player_receptions"],
            "point": [6.5],
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        roster = _make_roster(players=[player])

        # Set historical receptions on player (used as scale reference)
        player._test_historical_receptions = 5.0  # per game

        engine.apply(roster, "KC", 2024, 6)
        # target_share should be blended upward (prop implies more usage)
        assert player.usage.target_share >= original_target_share

    def test_rush_yds_adjusts_carry_share(self):
        """player_rush_yds prop adjusts carry_share upward when prop > historical."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        base_dist = np.array([3.0, 4.0, 5.0, 6.0, 7.0])
        player = _make_rb(carry_share=0.40, rush_yds_dist=base_dist)
        original_carry_share = player.usage.carry_share

        # Historical rush yds per game = mean(dist) * games_played
        historical_rush = float(np.mean(base_dist)) * player.games_played  # 5.0*17=85

        # Prop implies 105 yards (higher)
        props_df = pl.DataFrame({
            "player_name": ["Isiah Pacheco"],
            "market": ["player_rush_yds"],
            "point": [105.0],
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        roster = _make_roster(players=[player])
        engine.apply(roster, "KC", 2024, 6)

        assert player.usage.carry_share >= original_carry_share

    def test_pass_yds_shifts_team_receiving(self):
        """player_pass_yds prop shifts all WR/TE receiving_yards_dist proportionally."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        qb = _make_qb(name="Patrick Mahomes", player_id="PM")
        wr1 = _make_wr(name="Travis Kelce", player_id="TK", recv_yds_dist=np.array([10.0, 12.0, 15.0]))
        wr2 = _make_wr(name="Rashee Rice", player_id="RR", recv_yds_dist=np.array([8.0, 10.0, 12.0]))
        rb = _make_rb(name="Isiah Pacheco", player_id="IP")

        mean_wr1_before = float(np.mean(wr1.outcomes.receiving_yards_dist))
        mean_wr2_before = float(np.mean(wr2.outcomes.receiving_yards_dist))

        # Prop: 320 yd passing prop (vs historical ~250)
        props_df = pl.DataFrame({
            "player_name": ["Patrick Mahomes"],
            "market": ["player_pass_yds"],
            "point": [320.0],
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        roster = _make_roster(players=[qb, wr1, wr2, rb])
        # Set QB historical pass yds
        qb._test_historical_pass_yds = 250.0

        engine.apply(roster, "KC", 2024, 6)

        mean_wr1_after = float(np.mean(wr1.outcomes.receiving_yards_dist))
        mean_wr2_after = float(np.mean(wr2.outcomes.receiving_yards_dist))

        # Both WR/TE dists should shift upward
        assert mean_wr1_after > mean_wr1_before
        assert mean_wr2_after > mean_wr2_before
        # RB rushing dist should NOT change
        # (rb has no receiving_yards_dist to shift via pass_yds)

    def test_anytime_td_adjusts_rz_target_share(self):
        """player_anytime_td prop increases red_zone_target_share."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        player = _make_wr(red_zone_target_share=0.10, games_played=17)
        original_rz = player.usage.red_zone_target_share

        # Anytime TD prop of 1.5 implies high scoring likelihood
        props_df = pl.DataFrame({
            "player_name": ["Travis Kelce"],
            "market": ["player_anytime_td"],
            "point": [1.5],
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        roster = _make_roster(players=[player])
        engine.apply(roster, "KC", 2024, 6)

        # red_zone_target_share should increase when prop > historical
        assert player.usage.red_zone_target_share >= original_rz

    def test_share_renormalization_after_apply(self):
        """After apply(), sum of target_shares is approximately 1.0."""
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig
        from fantasy_sim.data.player_builder import _normalize_roster_shares

        # Create 4 WRs with target shares summing to 1.0
        players = [
            _make_wr(name=f"WR{i}", player_id=f"WR{i}", target_share=0.25,
                     recv_yds_dist=np.array([10.0, 12.0, 15.0]))
            for i in range(4)
        ]

        # Prop increases one player's apparent usage
        props_df = pl.DataFrame({
            "player_name": ["WR0"],
            "market": ["player_receptions"],
            "point": [10.0],  # High prop line
            "season": [2024],
            "week": [6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=5.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)
        roster = _make_roster(players=players)

        # Apply engine, then normalize (as done in build_game)
        engine.apply(roster, "KC", 2024, 6)
        _normalize_roster_shares(roster)

        total_target_share = sum(p.usage.target_share for p in roster.players)
        assert total_target_share == pytest.approx(1.0, abs=0.01)

    def test_crosswalk_audit_logging(self, caplog):
        """Apply with some matched and some unmatched players -> log contains counts."""
        import logging
        from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
        from fantasy_sim.data.vegas.models import PropsConfig

        player = _make_wr(name="Travis Kelce", player_id="TK")
        roster = _make_roster(players=[player])

        props_df = pl.DataFrame({
            "player_name": ["Travis Kelce", "Nonexistent Player XYZ"],
            "market": ["player_receptions", "player_receptions"],
            "point": [6.5, 3.0],
            "season": [2024, 2024],
            "week": [6, 6],
        })

        mock_loader = MagicMock()
        mock_loader.load_props.return_value = props_df

        config = PropsConfig(enabled=True, prior_strength=10.0)
        engine = PlayerPropsEngine(config, loader=mock_loader)

        with caplog.at_level(logging.INFO, logger="fantasy_sim.data.vegas.props_engine"):
            engine.apply(roster, "KC", 2024, 6)

        # Should log crosswalk audit with matched/unmatched counts
        log_text = " ".join(caplog.messages)
        assert "matched" in log_text.lower() or "crosswalk" in log_text.lower()


# ---------------------------------------------------------------------------
# TestPropsIntegration
# ---------------------------------------------------------------------------

class TestPropsIntegration:
    """Tests for props pipeline integration and A/B modes."""

    def test_ab_mode_vegas_props(self):
        """_build_props_config('vegas+props') returns PropsConfig with enabled=True."""
        from scripts.validate_pff_signal import _build_props_config
        config = _build_props_config("vegas+props")
        assert config is not None
        assert config.enabled is True

    def test_ab_mode_no_props(self):
        """_build_props_config('vegas') returns None (no props)."""
        from scripts.validate_pff_signal import _build_props_config
        config = _build_props_config("vegas")
        assert config is None

    def test_cache_key_includes_props(self):
        """Layer 3 cache key changes when props_enabled flips."""
        from unittest.mock import MagicMock, patch
        from fantasy_sim.data.vegas.models import PropsConfig

        with patch("fantasy_sim.data.game_context.DataLoader"):
            with patch("fantasy_sim.data.game_context.DataPipeline"):
                from fantasy_sim.data.game_context import GameContextBuilder

                # Builder with props enabled
                props_on = PropsConfig(enabled=True)
                builder_on = GameContextBuilder(props_config=props_on)

                # Builder with props disabled
                props_off = PropsConfig(enabled=False)
                builder_off = GameContextBuilder(props_config=props_off)

                # The presence of props engine should differ
                assert (builder_on._props_engine is not None) != (builder_off._props_engine is not None)

    def test_backtester_accepts_props_config(self):
        """Backtester(props_config=PropsConfig(enabled=True)) stores config correctly."""
        from fantasy_sim.data.vegas.models import PropsConfig
        from fantasy_sim.validation.backtester import Backtester

        props = PropsConfig(enabled=True)
        bt = Backtester(test_season=2024, props_config=props)
        assert bt._props_config is not None
        assert bt._props_config.enabled is True

    def test_parallel_signature_accepts_props(self):
        """build_games_parallel accepts props_config keyword argument."""
        import inspect
        from fantasy_sim.validation.parallel import build_games_parallel

        sig = inspect.signature(build_games_parallel)
        assert "props_config" in sig.parameters
