import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fantasy_sim.data.pipeline import DataPipeline


@pytest.fixture
def pipeline(tmp_path):
    return DataPipeline(cache_dir=tmp_path / "cache", seasons=[2024])


class TestDataPipeline:
    def test_build_returns_all_distribution_types(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)
        assert "play_calling" in result
        assert "play_outcomes" in result
        assert "turnover_rates" in result
        assert "kicking" in result
        assert "drive_start" in result

    def test_play_calling_has_teams(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)
        assert "KC" in result["play_calling"]
        assert "BUF" in result["play_calling"]

    def test_turnover_rates_has_teams(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)
        assert "KC" in result["turnover_rates"]
        assert "BUF" in result["turnover_rates"]

    def test_kicking_model_has_rates(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)
        assert "0_39" in result["kicking"].fg_make_rate
        assert "40_49" in result["kicking"].fg_make_rate
        assert "50_plus" in result["kicking"].fg_make_rate
