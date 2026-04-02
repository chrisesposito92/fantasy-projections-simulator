"""Integration tests for TalentStabilizer wired into GameContextBuilder."""

from __future__ import annotations

import pytest

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import PffConfig, TalentConfig, MatchupConfig


class TestTalentIntegration:
    def test_builder_accepts_pff_config_with_talent(self):
        """GameContextBuilder should accept PffConfig with talent enabled."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(enabled=True),
            matchup=MatchupConfig(enabled=False),
        )
        builder = GameContextBuilder(pff_config=config)
        assert builder._pff_config.talent.enabled is True

    def test_builder_disabled_pff_has_no_stabilizer(self):
        """Default builder has no talent stabilizer."""
        builder = GameContextBuilder()
        assert builder._talent_stabilizer is None

    def test_builder_with_both_layers(self):
        """Both matchup and talent can be enabled simultaneously."""
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=True),
            talent=TalentConfig(enabled=True),
        )
        builder = GameContextBuilder(pff_config=config)
        # Neither engine initializes without PFF data on disk, but config is accepted
        assert builder._pff_config.matchup.enabled is True
        assert builder._pff_config.talent.enabled is True

    def test_builder_talent_enabled_no_data_has_no_stabilizer(self):
        """When PFF is enabled with talent but data is unavailable, stabilizer stays None."""
        config = PffConfig(
            enabled=True,
            data_dir="/nonexistent/path/that/does/not/exist",
            talent=TalentConfig(enabled=True),
            matchup=MatchupConfig(enabled=False),
        )
        builder = GameContextBuilder(pff_config=config)
        assert builder._talent_stabilizer is None

    def test_builder_pff_disabled_has_no_stabilizer(self):
        """PffConfig with enabled=False never creates a stabilizer."""
        config = PffConfig(
            enabled=False,
            talent=TalentConfig(enabled=True),
        )
        builder = GameContextBuilder(pff_config=config)
        assert builder._talent_stabilizer is None

    def test_builder_talent_disabled_has_no_stabilizer(self):
        """PffConfig with talent.enabled=False never creates a stabilizer."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(enabled=False),
        )
        builder = GameContextBuilder(pff_config=config)
        assert builder._talent_stabilizer is None

    def test_pff_crosswalk_starts_none(self):
        """_pff_crosswalk is None by default (None sentinel used for caching)."""
        builder = GameContextBuilder()
        assert builder._pff_crosswalk is None

    def test_pff_loader_starts_none(self):
        """_pff_loader is None when PFF is disabled."""
        builder = GameContextBuilder()
        assert builder._pff_loader is None
