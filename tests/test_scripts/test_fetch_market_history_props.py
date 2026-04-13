from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "fetch_market_history_props.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fetch_market_history_props_under_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_cli_defaults_snapshot_label_to_close_core8():
    module = _load_script_module()

    args = module.build_cli().parse_args(["--season", "2024"])

    assert args.snapshot_label == "close_core8"
