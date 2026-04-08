from pathlib import Path
import polars as pl
import nflreadpy


DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"


class DataLoader:
    """Wraps nflreadpy with filesystem caching via parquet files."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, name: str, seasons: list[int]) -> Path:
        season_str = "_".join(str(s) for s in sorted(seasons))
        return self.cache_dir / f"{name}_{season_str}.parquet"

    def _load_cached(self, cache_path: Path) -> pl.DataFrame | None:
        if cache_path.exists():
            return pl.read_parquet(cache_path)
        return None

    def _save_cache(self, df: pl.DataFrame, cache_path: Path) -> None:
        df.write_parquet(cache_path)

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
        # Normalize nflverse column names to our standard names
        rename_map = {}
        if "gsis_id" in df.columns and "player_id" not in df.columns:
            rename_map["gsis_id"] = "player_id"
        if "full_name" in df.columns and "player_name" not in df.columns:
            rename_map["full_name"] = "player_name"
        if rename_map:
            df = df.rename(rename_map)
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
