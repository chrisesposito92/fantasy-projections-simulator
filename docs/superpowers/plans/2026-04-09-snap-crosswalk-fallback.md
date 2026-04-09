# Snap Crosswalk Fallback Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce snap crosswalk unmatched players from 0.5-1.4% to ~0% by adding case-insensitive/suffix-normalized Tier 2 matching and a manual crosswalk override dict.

**Architecture:** Three changes to `_build_snap_crosswalk()` in priority order: Tier 0 manual dict (checked first, authoritative override), enhanced Tier 2 (case-insensitive + suffix/middle-name stripping), and YAML config for the manual dict. No new files; changes to `engine.py`, `models.py`, `config.py`, `defaults.yaml`, and tests.

**Tech Stack:** Python 3.12+, polars, re (stdlib), pytest

---

### Task 1: Add `_normalize_name()` helper with tests

**Files:**
- Create: `tests/test_data/test_usage/test_normalize_name.py`
- Modify: `src/fantasy_sim/data/usage/engine.py:17-30` (add import + helper)

- [ ] **Step 1: Write failing tests for `_normalize_name()`**

Create `tests/test_data/test_usage/test_normalize_name.py`:

```python
"""Tests for _normalize_name() helper used in snap crosswalk Tier 2 matching."""

from __future__ import annotations

import pytest

from fantasy_sim.data.usage.engine import _normalize_name


class TestNormalizeName:
    """Unit tests for _normalize_name(): suffix stripping, case folding, middle names."""

    def test_lowercase(self):
        assert _normalize_name("Grant DuBose") == "grant dubose"

    def test_strip_jr_dot(self):
        assert _normalize_name("Kevin Austin Jr.") == "kevin austin"

    def test_strip_jr_no_dot(self):
        assert _normalize_name("Velus Jones Jr") == "velus jones"

    def test_strip_sr_dot(self):
        assert _normalize_name("Gary Smith Sr.") == "gary smith"

    def test_strip_ii(self):
        assert _normalize_name("Kwamie Lassiter II") == "kwamie lassiter"

    def test_strip_iii(self):
        assert _normalize_name("Kenneth Walker III") == "kenneth walker"

    def test_strip_iv(self):
        assert _normalize_name("John Doe IV") == "john doe"

    def test_strip_v(self):
        assert _normalize_name("Henry Thomas V") == "henry thomas"

    def test_middle_name_collapsed(self):
        """Middle names are dropped: first + last only."""
        assert _normalize_name("John Samuel Shenker") == "john shenker"

    def test_periods_stripped(self):
        assert _normalize_name("D.J. Turner") == "dj turner"

    def test_apostrophe_preserved(self):
        """Apostrophes in names like D'Vonte are preserved."""
        assert _normalize_name("D'Vonte Price") == "d'vonte price"

    def test_no_suffix_unchanged(self):
        assert _normalize_name("Rodney Williams") == "rodney williams"

    def test_two_word_name_unchanged(self):
        assert _normalize_name("Pat Mahomes") == "pat mahomes"

    def test_whitespace_trimmed(self):
        assert _normalize_name("  Kenneth Walker III  ") == "kenneth walker"

    def test_suffix_ii_not_stripped_from_middle(self):
        """II is only stripped at end of name, not from middle."""
        # Edge case: if someone had II in their actual name mid-string
        assert _normalize_name("II Smith Jones") == "ii jones"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_usage/test_normalize_name.py -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_name'`

- [ ] **Step 3: Implement `_normalize_name()` in engine.py**

Add `import re` to the imports block at the top of `engine.py` (after line 20, `import logging`):

```python
import re
```

Add the helper function and regex constant after the `_LEAGUE_AVG_SNAP_SHARE` constant (after line 34):

```python
_SUFFIXES_RE = re.compile(r'\s+(jr\.?|sr\.?|ii|iii|iv|v)\s*$', re.IGNORECASE)


def _normalize_name(name: str) -> str:
    """Normalize player name for fuzzy Tier 2 matching.

    Lowercases, strips suffixes (Jr./Sr./II/III/IV/V),
    removes periods, collapses to first + last name only.
    """
    name = name.lower().strip()
    name = _SUFFIXES_RE.sub('', name)
    name = name.replace('.', '').strip()
    parts = name.split()
    if len(parts) > 2:
        parts = [parts[0], parts[-1]]
    return ' '.join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_usage/test_normalize_name.py -v`
Expected: all 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_data/test_usage/test_normalize_name.py src/fantasy_sim/data/usage/engine.py
git commit -m "feat: add _normalize_name() helper for snap crosswalk Tier 2"
```

---

### Task 2: Add `manual_crosswalk` to config pipeline

**Files:**
- Modify: `src/fantasy_sim/data/usage/models.py:9-14` (add field to SnapConfig)
- Modify: `src/fantasy_sim/data/usage/config.py:34-37` (parse from YAML)
- Modify: `config/defaults.yaml:215-218` (add manual_crosswalk)
- Test: `tests/test_data/test_usage/test_usage_engine.py` (existing TestUsageConfigDefaults)

- [ ] **Step 1: Write failing test for `manual_crosswalk` default**

Add to `tests/test_data/test_usage/test_usage_engine.py` inside `TestUsageConfigDefaults` class (after the existing config tests around line 219):

```python
    def test_snap_manual_crosswalk_default_empty(self):
        cfg = SnapConfig()
        assert cfg.manual_crosswalk == {}
        assert isinstance(cfg.manual_crosswalk, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestUsageConfigDefaults::test_snap_manual_crosswalk_default_empty -v`
Expected: FAIL with `AttributeError: ... has no attribute 'manual_crosswalk'`

- [ ] **Step 3: Add `manual_crosswalk` field to `SnapConfig`**

In `src/fantasy_sim/data/usage/models.py`, add the field to `SnapConfig` (after line 14, `factor_clamp`):

```python
    manual_crosswalk: dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestUsageConfigDefaults::test_snap_manual_crosswalk_default_empty -v`
Expected: PASS

- [ ] **Step 5: Write failing test for config parser**

Add a new test to `tests/test_data/test_usage/test_usage_engine.py` inside `TestUsageConfigDefaults`:

```python
    def test_load_usage_config_parses_manual_crosswalk(self):
        from fantasy_sim.data.usage.config import load_usage_config
        defaults = {
            "usage": {
                "snap": {
                    "manual_crosswalk": {
                        "WoodMi00": "00-0037300",
                        "LassKw00": "00-0037420",
                    }
                }
            }
        }
        cfg = load_usage_config(defaults)
        assert cfg.snap.manual_crosswalk == {
            "WoodMi00": "00-0037300",
            "LassKw00": "00-0037420",
        }

    def test_load_usage_config_manual_crosswalk_defaults_empty(self):
        from fantasy_sim.data.usage.config import load_usage_config
        defaults = {"usage": {"snap": {}}}
        cfg = load_usage_config(defaults)
        assert cfg.snap.manual_crosswalk == {}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestUsageConfigDefaults::test_load_usage_config_parses_manual_crosswalk tests/test_data/test_usage/test_usage_engine.py::TestUsageConfigDefaults::test_load_usage_config_manual_crosswalk_defaults_empty -v`
Expected: FAIL (manual_crosswalk not parsed — SnapConfig gets default empty dict regardless of YAML input)

- [ ] **Step 7: Update config parser to read `manual_crosswalk`**

In `src/fantasy_sim/data/usage/config.py`, update the `SnapConfig` construction (line 34-37) to include `manual_crosswalk`:

```python
        snap=SnapConfig(
            prior_strength=snap_d.get("prior_strength", 8.0),
            min_games=snap_d.get("min_games", 4),
            factor_clamp=tuple(snap_d.get("factor_clamp", [0.70, 1.30])),
            manual_crosswalk=snap_d.get("manual_crosswalk", {}),
        ),
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestUsageConfigDefaults -v`
Expected: all tests PASS

- [ ] **Step 9: Add `manual_crosswalk` to `defaults.yaml`**

In `config/defaults.yaml`, add `manual_crosswalk` under `usage.snap` (after `factor_clamp` on line 218):

```yaml
  snap:
    prior_strength: 8.0
    min_games: 4
    factor_clamp: [0.70, 1.30]
    manual_crosswalk:
      # Name variants that automated matching cannot resolve
      WoodMi00: "00-0037300"   # Michael Woods II -> Mike Woods (CLE)
      # PFR ID mismatches between snap data and roster data
      LassKw00: "00-0037420"   # Kwamie Lassiter II (snap LassKw00 != roster LassKw20)
```

- [ ] **Step 10: Commit**

```bash
git add src/fantasy_sim/data/usage/models.py src/fantasy_sim/data/usage/config.py config/defaults.yaml tests/test_data/test_usage/test_usage_engine.py
git commit -m "feat: add manual_crosswalk config for snap crosswalk overrides"
```

---

### Task 3: Implement Tier 0 (manual crosswalk) in `_build_snap_crosswalk()`

**Files:**
- Modify: `src/fantasy_sim/data/usage/engine.py:189-296` (`_build_snap_crosswalk` method)
- Test: `tests/test_data/test_usage/test_usage_engine.py` (TestCrosswalk class)

- [ ] **Step 1: Write failing test for Tier 0 manual override**

Add to `tests/test_data/test_usage/test_usage_engine.py` inside the `TestCrosswalk` class (after line 415):

```python
    def test_crosswalk_manual_override_applied_first(self, mock_snap_df, mock_roster_df):
        """Manual crosswalk entries are applied before automated matching (Tier 0)."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = mock_snap_df
        loader.load_rosters.return_value = mock_roster_df

        config = UsageConfig(
            snap=SnapConfig(manual_crosswalk={"WR001": "manual-gsis-override"})
        )
        engine = UsageEngine(config=config, loader=loader)
        crosswalk = engine._build_snap_crosswalk(2024)

        # Manual override takes precedence over Tier 1 pfr_id join
        assert crosswalk["WR001"] == "manual-gsis-override"
        # Other players still matched via Tier 1
        assert crosswalk["RB001"] == "gsis-rb1"

    def test_crosswalk_manual_override_for_missing_player(self, mock_snap_df, mock_roster_df):
        """Manual crosswalk resolves players that Tier 1 and Tier 2 cannot match."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        # Add an unmatched player to snap data
        extra_row = pl.DataFrame({
            "pfr_player_id": ["UNKNOWN01"],
            "player": ["Mystery Player"],
            "position": ["WR"],
            "team": ["KC"],
            "season": [2024],
            "week": [1],
            "game_type": ["REG"],
            "offense_snaps": [40],
            "offense_pct": [0.57],
        })
        snap_with_extra = pl.concat([mock_snap_df, extra_row])

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = snap_with_extra
        loader.load_rosters.return_value = mock_roster_df

        config = UsageConfig(
            snap=SnapConfig(manual_crosswalk={"UNKNOWN01": "gsis-mystery"})
        )
        engine = UsageEngine(config=config, loader=loader)
        crosswalk = engine._build_snap_crosswalk(2024)

        assert crosswalk["UNKNOWN01"] == "gsis-mystery"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk::test_crosswalk_manual_override_applied_first tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk::test_crosswalk_manual_override_for_missing_player -v`
Expected: FAIL (manual_crosswalk not used in `_build_snap_crosswalk` yet)

- [ ] **Step 3: Add Tier 0 to `_build_snap_crosswalk()`**

In `src/fantasy_sim/data/usage/engine.py`, inside `_build_snap_crosswalk()`, after the empty crosswalk dict is created (line 235, `crosswalk: dict[str, str] = {}`), add Tier 0 before Tier 1:

```python
        crosswalk: dict[str, str] = {}

        # --- Tier 0: manual crosswalk overrides (authoritative) ---
        manual = self._config.snap.manual_crosswalk
        if manual:
            all_pfr_ids_in_snap = set(
                skill_snap_df.select("pfr_player_id").unique().to_series().to_list()
            )
            for pfr_id, gsis_id in manual.items():
                if pfr_id in all_pfr_ids_in_snap:
                    crosswalk[pfr_id] = gsis_id
            if crosswalk:
                logger.info(
                    "Snap crosswalk: %d manual overrides applied", len(crosswalk)
                )
```

Then update the Tier 1 matched loop to skip already-matched PFR IDs (around line 236):

```python
        for row in matched.unique(subset=["pfr_player_id"]).iter_rows(named=True):
            if row["pfr_player_id"] not in crosswalk:  # don't override Tier 0
                crosswalk[row["pfr_player_id"]] = row["gsis_id"]
```

And similarly in the Tier 2 matched loop (around line 268), the existing `if row["pfr_player_id"] not in crosswalk:` check already prevents overrides, so no change needed there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk -v`
Expected: all crosswalk tests PASS (including new Tier 0 tests + existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/usage/engine.py tests/test_data/test_usage/test_usage_engine.py
git commit -m "feat: add Tier 0 manual crosswalk override to _build_snap_crosswalk"
```

---

### Task 4: Enhance Tier 2 with case-insensitive + normalized name matching

**Files:**
- Modify: `src/fantasy_sim/data/usage/engine.py:239-275` (Tier 2 section of `_build_snap_crosswalk`)
- Test: `tests/test_data/test_usage/test_usage_engine.py` (TestCrosswalk class)

- [ ] **Step 1: Write failing tests for enhanced Tier 2**

Add to `tests/test_data/test_usage/test_usage_engine.py` inside the `TestCrosswalk` class:

```python
    def test_crosswalk_tier2_case_insensitive(self, mock_roster_df):
        """Tier 2 matches despite capitalization differences (e.g., Dubose vs DuBose)."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        # Snap data has "Grant Dubose" (lowercase b), roster has "Grant DuBose" (capital B)
        snap_df = pl.DataFrame({
            "pfr_player_id": ["DuboGr00"],
            "player": ["Grant Dubose"],
            "position": ["WR"],
            "team": ["MIA"],
            "season": [2024],
            "week": [1],
            "game_type": ["REG"],
            "offense_snaps": [30],
            "offense_pct": [0.43],
        })
        roster_df = pl.DataFrame({
            "player_id": ["gsis-dubose"],
            "pfr_id": [None],  # null pfr_id -> Tier 1 fails -> falls to Tier 2
            "full_name": ["Grant DuBose"],
            "position": ["WR"],
            "team": ["MIA"],
            "season": [2024],
            "week": [1],
        })

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = snap_df
        loader.load_rosters.return_value = roster_df

        engine = UsageEngine(config=UsageConfig(), loader=loader)
        crosswalk = engine._build_snap_crosswalk(2024)

        assert crosswalk.get("DuboGr00") == "gsis-dubose"

    def test_crosswalk_tier2_suffix_stripped(self, mock_roster_df):
        """Tier 2 matches when snap has 'Kevin Austin' but roster has 'Kevin Austin Jr.'."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        snap_df = pl.DataFrame({
            "pfr_player_id": ["AustKe00"],
            "player": ["Kevin Austin"],
            "position": ["WR"],
            "team": ["NO"],
            "season": [2024],
            "week": [1],
            "game_type": ["REG"],
            "offense_snaps": [25],
            "offense_pct": [0.36],
        })
        roster_df = pl.DataFrame({
            "player_id": ["gsis-austin"],
            "pfr_id": [None],
            "full_name": ["Kevin Austin Jr."],
            "position": ["WR"],
            "team": ["NO"],
            "season": [2024],
            "week": [1],
        })

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = snap_df
        loader.load_rosters.return_value = roster_df

        engine = UsageEngine(config=UsageConfig(), loader=loader)
        crosswalk = engine._build_snap_crosswalk(2024)

        assert crosswalk.get("AustKe00") == "gsis-austin"

    def test_crosswalk_tier2_middle_name_collapsed(self):
        """Tier 2 matches when snap has 'John Samuel Shenker' but roster has 'John Shenker'."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        snap_df = pl.DataFrame({
            "pfr_player_id": ["ShenJo00"],
            "player": ["John Samuel Shenker"],
            "position": ["TE"],
            "team": ["LV"],
            "season": [2024],
            "week": [1],
            "game_type": ["REG"],
            "offense_snaps": [20],
            "offense_pct": [0.29],
        })
        roster_df = pl.DataFrame({
            "player_id": ["gsis-shenker"],
            "pfr_id": [None],
            "full_name": ["John Shenker"],
            "position": ["TE"],
            "team": ["LV"],
            "season": [2024],
            "week": [1],
        })

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = snap_df
        loader.load_rosters.return_value = roster_df

        engine = UsageEngine(config=UsageConfig(), loader=loader)
        crosswalk = engine._build_snap_crosswalk(2024)

        assert crosswalk.get("ShenJo00") == "gsis-shenker"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk::test_crosswalk_tier2_case_insensitive tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk::test_crosswalk_tier2_suffix_stripped tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk::test_crosswalk_tier2_middle_name_collapsed -v`
Expected: FAIL (all three, Tier 2 still uses exact name matching)

- [ ] **Step 3: Enhance Tier 2 in `_build_snap_crosswalk()`**

In `src/fantasy_sim/data/usage/engine.py`, replace the Tier 2 section (starting from the `if len(unmatched_pfr_ids) > 0:` block, approximately lines 246-275) with:

```python
        if len(unmatched_pfr_ids) > 0:
            name_col = (
                "full_name" if "full_name" in roster_df.columns
                else "player_name" if "player_name" in roster_df.columns
                else None
            )
            if name_col is not None:
                # Add normalized name columns for fuzzy matching
                unmatched_with_norm = unmatched_pfr_ids.with_columns(
                    pl.col("player").map_elements(
                        _normalize_name, return_dtype=pl.Utf8
                    ).alias("norm_name")
                )
                roster_name_map = (
                    roster_df
                    .filter(pl.col("gsis_id").is_not_null())
                    .with_columns(
                        pl.col(name_col).map_elements(
                            _normalize_name, return_dtype=pl.Utf8
                        ).alias("norm_name")
                    )
                    .select(["norm_name", "team", "gsis_id"])
                    .unique(subset=["norm_name", "team"], keep="first")
                )
                name_joined = unmatched_with_norm.join(
                    roster_name_map,
                    on=["norm_name", "team"],
                    how="inner",
                )
                tier2_count = 0
                for row in name_joined.iter_rows(named=True):
                    if row["pfr_player_id"] not in crosswalk:
                        crosswalk[row["pfr_player_id"]] = row["gsis_id"]
                        tier2_count += 1
                if tier2_count > 0:
                    logger.info(
                        "Snap crosswalk: %d players matched via name+team fallback",
                        tier2_count,
                    )
```

Note: The roster DataFrame uses `gsis_id` after the rename check at lines 208-209. The unmatched DataFrame already has `player` and `team` columns from the snap data.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_usage/test_usage_engine.py::TestCrosswalk -v`
Expected: all crosswalk tests PASS (new Tier 2 tests + existing + Tier 0 tests)

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/test_data/test_usage/ -v`
Expected: all usage tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/usage/engine.py tests/test_data/test_usage/test_usage_engine.py
git commit -m "feat: enhance Tier 2 crosswalk with case-insensitive + normalized name matching"
```

---

### Task 5: Full regression test

**Files:**
- Test: all existing tests

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: all tests PASS, no regressions

- [ ] **Step 2: Run ruff lint check**

Run: `uv run ruff check src/fantasy_sim/data/usage/engine.py src/fantasy_sim/data/usage/models.py src/fantasy_sim/data/usage/config.py`
Expected: no lint errors

- [ ] **Step 3: Fix any issues found, then commit if needed**

If any fixes were needed:
```bash
git add -u
git commit -m "fix: address lint/test issues from crosswalk fallback changes"
```
