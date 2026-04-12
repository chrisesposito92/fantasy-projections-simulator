from pathlib import Path
import polars as pl
import nflreadpy


DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"


class DataLoader:
    """Wraps nflreadpy with filesystem caching via parquet files."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[Path, pl.DataFrame] = {}

    def _cache_key(self, name: str, seasons: list[int]) -> Path:
        season_str = "_".join(str(s) for s in sorted(seasons))
        return self.cache_dir / f"{name}_{season_str}.parquet"

    def _load_cached(self, cache_path: Path) -> pl.DataFrame | None:
        if cache_path in self._memory_cache:
            return self._memory_cache[cache_path]
        if cache_path.exists():
            df = pl.read_parquet(cache_path)
            self._memory_cache[cache_path] = df
            return df
        return None

    def _save_cache(self, df: pl.DataFrame, cache_path: Path) -> None:
        df.write_parquet(cache_path)
        self._memory_cache[cache_path] = df

    def _normalize_player_identity_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Map nflverse player identity columns to the loader's standard names."""
        rename_map = {}
        if "gsis_id" in df.columns and "player_id" not in df.columns:
            rename_map["gsis_id"] = "player_id"
        if "full_name" in df.columns and "player_name" not in df.columns:
            rename_map["full_name"] = "player_name"
        if rename_map:
            return df.rename(rename_map)
        return df

    def load_pbp(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("pbp", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_pbp(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_player_stats(self, seasons: list[int], summary_level: str = "week") -> pl.DataFrame:
        cache_path = self._cache_key(f"player_stats_{summary_level}", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_player_stats(seasons, summary_level=summary_level)
        self._save_cache(df, cache_path)
        return df

    def load_rosters(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("rosters_weekly", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_rosters_weekly(seasons)
        df = self._normalize_player_identity_columns(df)
        self._save_cache(df, cache_path)
        return df

    def load_injuries(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("injuries", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached

        df = nflreadpy.load_injuries(seasons)
        df = self._normalize_player_identity_columns(df)
        self._save_cache(df, cache_path)
        return df

    def load_schedules(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("schedules", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_schedules(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_snap_counts(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("snap_counts", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_snap_counts(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_nextgen_stats(self, seasons: list[int], stat_type: str = "receiving") -> pl.DataFrame:
        cache_path = self._cache_key(f"ngs_{stat_type}", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_nextgen_stats(seasons, stat_type=stat_type)
        self._save_cache(df, cache_path)
        return df

    def load_pff_facet(
        self,
        facet: str,
        seasons: list[int],
        pff_dir: Path | None = None,
    ) -> pl.DataFrame:
        """Load a PFF processed facet from local parquet cache.

        Reads from ``~/.fantasy-sim/pff/processed/`` (or ``pff_dir`` override).
        Returns empty DataFrame if no files are found.

        Args:
            facet: PFF facet name (e.g. ``"receiving_summary"``).
            seasons: List of seasons to load.
            pff_dir: Override directory; defaults to ``~/.fantasy-sim/pff/processed/``.

        Returns:
            Concatenated DataFrame, or empty DataFrame if no data found.
        """
        DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed"
        target_dir = pff_dir or DEFAULT_PFF_DIR
        frames: list[pl.DataFrame] = []
        for season in seasons:
            path = target_dir / f"{facet}_{season}.parquet"
            if path.exists():
                frames.append(pl.read_parquet(path))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    def load_depth_charts(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("depth_charts", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_depth_charts(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_draft_picks(self) -> pl.DataFrame:
        cache_path = self.cache_dir / "draft_picks.parquet"
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_draft_picks()
        self._save_cache(df, cache_path)
        return df

    def clear_cache(self) -> None:
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
        self._memory_cache.clear()
