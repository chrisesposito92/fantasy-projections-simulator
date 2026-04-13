from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


def _load_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "backfill_tracking_data.py"
    spec = importlib.util.spec_from_file_location("backfill_tracking_data_under_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_tracking_data_loads_all_required_sources():
    module = _load_script_module()
    loader = MagicMock()

    with patch.object(module, "DataLoader", return_value=loader):
        module.main(["--seasons", "2022", "2023"])

    assert loader.load_participation.call_args_list == [call([2022]), call([2023])]
    assert loader.load_ftn_charting.call_args_list == [call([2022]), call([2023])]
    assert loader.load_nextgen_stats.call_args_list == [
        call([2022], stat_type="passing"),
        call([2022], stat_type="rushing"),
        call([2023], stat_type="passing"),
        call([2023], stat_type="rushing"),
    ]


def test_backfill_tracking_data_rejects_pre_2022_seasons(capsys):
    module = _load_script_module()

    with pytest.raises(SystemExit) as excinfo:
        module.main(["--seasons", "2021"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "season must be 2022 or later" in captured.err
