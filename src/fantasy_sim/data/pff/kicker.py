"""PFF Kicker Engine — per-kicker FG accuracy with Bayesian shrinkage."""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import KickerConfig
from fantasy_sim.models.distributions import KickingModel

logger = logging.getLogger(__name__)

_SHORT_BUCKETS = ("one", "twenty", "thirty")


class KickerEngine:
    """Computes per-kicker KickingModel from PFF field goal accuracy data."""

    def __init__(self, config: KickerConfig, pff_loader: PffLoader, training_seasons: list[int]) -> None:
        self._config = config
        self._data = pff_loader.load_facet("field_goal_summary", training_seasons)
        self._league_rates = self._compute_league_rates()
        self._nfl_to_pff: dict[str, int] = {}
        self._pff_to_nfl: dict[int, str] = {}

    def build_crosswalk(self, roster: pl.DataFrame, season: int) -> None:
        """Build kicker crosswalk. Layer 1: pff_id match. Layer 2: name+team."""
        if self._data.is_empty() or roster.is_empty():
            return

        pff_kickers = self._data.select(["player_id", "player", "team"]).unique(subset=["player_id"])
        if pff_kickers.is_empty():
            return

        # Layer 1: pff_id match
        if "pff_id" in roster.columns:
            kicker_roster = (
                roster.filter(pl.col("position") == "K")
                .filter(pl.col("pff_id").is_not_null())
                .with_columns(pl.col("pff_id").cast(pl.Utf8).cast(pl.Int64, strict=False).alias("_pff_id_int"))
                .filter(pl.col("_pff_id_int").is_not_null())
                .select(["player_id", "_pff_id_int"])
                .unique(subset=["_pff_id_int"])
            )
            matched = pff_kickers.join(kicker_roster, left_on="player_id", right_on="_pff_id_int", how="inner")
            for row in matched.iter_rows(named=True):
                self._pff_to_nfl[row["player_id"]] = row["player_id_right"]
                self._nfl_to_pff[row["player_id_right"]] = row["player_id"]

        # Layer 2: name+team fallback
        unmatched = pff_kickers.filter(~pl.col("player_id").is_in(list(self._pff_to_nfl.keys())))
        if not unmatched.is_empty():
            kicker_lookup = (
                roster.filter(pl.col("position") == "K")
                .select(["player_id", "player_name", "team"])
                .unique(subset=["player_id"])
            )
            name_matched = unmatched.join(
                kicker_lookup,
                left_on=["player", "team"],
                right_on=["player_name", "team"],
                how="inner",
            )
            for row in name_matched.iter_rows(named=True):
                self._pff_to_nfl[row["player_id"]] = row["player_id_right"]
                self._nfl_to_pff[row["player_id_right"]] = row["player_id"]

        logger.info("Kicker crosswalk: %d/%d matched", len(self._pff_to_nfl), pff_kickers.height)

    def _compute_league_rates(self) -> dict[str, float]:
        if self._data.is_empty():
            return {"0_39": 0.90, "40_49": 0.84, "50_plus": 0.67, "xp": 0.95}

        short_att, short_made = 0, 0
        for bucket in _SHORT_BUCKETS:
            att_col, made_col = f"{bucket}_attempts", f"{bucket}_made"
            if att_col in self._data.columns and made_col in self._data.columns:
                short_att += self._data[att_col].fill_null(0).sum()
                short_made += self._data[made_col].fill_null(0).sum()

        def _safe(made: int, att: int, fb: float) -> float:
            return made / att if att > 0 else fb

        forty_att = self._data["forty_attempts"].fill_null(0).sum() if "forty_attempts" in self._data.columns else 0
        forty_made = self._data["forty_made"].fill_null(0).sum() if "forty_made" in self._data.columns else 0
        fifty_att = self._data["fifty_attempts"].fill_null(0).sum() if "fifty_attempts" in self._data.columns else 0
        fifty_made = self._data["fifty_made"].fill_null(0).sum() if "fifty_made" in self._data.columns else 0
        pat_att = self._data["pat_attempts"].fill_null(0).sum() if "pat_attempts" in self._data.columns else 0
        pat_made = self._data["pat_made"].fill_null(0).sum() if "pat_made" in self._data.columns else 0

        return {
            "0_39": _safe(short_made, short_att, 0.90),
            "40_49": _safe(forty_made, forty_att, 0.84),
            "50_plus": _safe(fifty_made, fifty_att, 0.67),
            "xp": _safe(pat_made, pat_att, 0.95),
        }

    def compute(self, kicker_player_id: str) -> KickingModel | None:
        """Compute KickingModel for a kicker given their nflverse player_id.

        Returns None if:
        - Not in the crosswalk.
        - Fewer than min_attempts total FG attempts.
        """
        pff_id = self._nfl_to_pff.get(kicker_player_id)
        if pff_id is None:
            return None

        kicker_data = self._data.filter(pl.col("player_id") == pff_id)
        if kicker_data.is_empty():
            return None

        total_fg_att = 0
        for bucket in list(_SHORT_BUCKETS) + ["forty", "fifty"]:
            att_col = f"{bucket}_attempts"
            if att_col in kicker_data.columns:
                total_fg_att += kicker_data[att_col].fill_null(0).sum()
        if total_fg_att < self._config.min_attempts:
            return None

        prior = self._config.prior_strength

        def _shrink(made: int, att: int, league_key: str) -> float:
            league = self._league_rates[league_key]
            return (made + prior * league) / (att + prior)

        short_att, short_made = 0, 0
        for bucket in _SHORT_BUCKETS:
            att_col, made_col = f"{bucket}_attempts", f"{bucket}_made"
            if att_col in kicker_data.columns and made_col in kicker_data.columns:
                short_att += kicker_data[att_col].fill_null(0).sum()
                short_made += kicker_data[made_col].fill_null(0).sum()

        forty_att = kicker_data["forty_attempts"].fill_null(0).sum() if "forty_attempts" in kicker_data.columns else 0
        forty_made = kicker_data["forty_made"].fill_null(0).sum() if "forty_made" in kicker_data.columns else 0
        fifty_att = kicker_data["fifty_attempts"].fill_null(0).sum() if "fifty_attempts" in kicker_data.columns else 0
        fifty_made = kicker_data["fifty_made"].fill_null(0).sum() if "fifty_made" in kicker_data.columns else 0
        pat_att = kicker_data["pat_attempts"].fill_null(0).sum() if "pat_attempts" in kicker_data.columns else 0
        pat_made = kicker_data["pat_made"].fill_null(0).sum() if "pat_made" in kicker_data.columns else 0

        return KickingModel(
            fg_make_rate={
                "0_39": float(_shrink(short_made, short_att, "0_39")),
                "40_49": float(_shrink(forty_made, forty_att, "40_49")),
                "50_plus": float(_shrink(fifty_made, fifty_att, "50_plus")),
            },
            xp_rate=float(_shrink(pat_made, pat_att, "xp")),
        )
