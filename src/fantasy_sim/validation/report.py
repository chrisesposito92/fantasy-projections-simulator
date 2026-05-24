from rich.console import Console
from rich.table import Table
from fantasy_sim.validation.backtester import BacktestResult, STAT_KS_DISPLAY_ROWS


def _add_ks_row(table: Table, position: str, stat: str, row: dict[str, float | int]) -> None:
    table.add_row(
        position,
        stat,
        f"{float(row['ks']):.2f}",
        f"{float(row['projected_mean']):.1f}",
        f"{float(row['actual_mean']):.1f}",
        f"{float(row['mean_delta']):+.1f}",
        str(int(row["n"])),
    )


def format_backtest_report(result: BacktestResult) -> str:
    """Format a BacktestResult as a readable report string."""
    console = Console(width=160, force_terminal=True)

    with console.capture() as capture:
        console.print(f"\n[bold]Backtest Report — {result.test_season} Season[/bold]")
        console.print(f"Players evaluated: {result.total_players_evaluated}")
        console.print(f"Weeks evaluated: {result.total_weeks_evaluated}\n")

        table = Table(title="Accuracy Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Target", justify="right")
        table.add_column("Status", justify="center")

        # Weekly MAE
        weekly_status = "PASS" if result.weekly_mae <= BacktestResult.WEEKLY_MAE_TARGET else "FAIL"
        weekly_style = "green" if weekly_status == "PASS" else "red"
        table.add_row(
            "Weekly MAE",
            f"{result.weekly_mae:.2f}",
            f"< {BacktestResult.WEEKLY_MAE_TARGET:.1f}",
            f"[{weekly_style}]{weekly_status}[/{weekly_style}]",
        )

        # Season MAE
        season_status = "PASS" if result.season_mae <= BacktestResult.SEASON_MAE_TARGET else "FAIL"
        season_style = "green" if season_status == "PASS" else "red"
        table.add_row(
            "Season Total MAE",
            f"{result.season_mae:.1f}",
            f"< {BacktestResult.SEASON_MAE_TARGET:.1f}",
            f"[{season_style}]{season_status}[/{season_style}]",
        )

        # Rank correlations by position
        for pos in ["QB", "RB", "WR", "TE"]:
            corr = result.rank_correlations.get(pos, 0.0)
            corr_status = "PASS" if corr >= BacktestResult.RANK_CORR_TARGET else "FAIL"
            corr_style = "green" if corr_status == "PASS" else "red"
            table.add_row(
                f"Rank Corr ({pos})",
                f"{corr:.3f}",
                f"> {BacktestResult.RANK_CORR_TARGET:.2f}",
                f"[{corr_style}]{corr_status}[/{corr_style}]",
            )

        # Boom/bust calibration
        cal_status = "PASS" if result.boom_bust_calibration <= BacktestResult.CALIBRATION_TARGET else "FAIL"
        cal_style = "green" if cal_status == "PASS" else "red"
        table.add_row(
            "Boom/Bust Calibration",
            f"{result.boom_bust_calibration:.3f}",
            f"< {BacktestResult.CALIBRATION_TARGET:.2f}",
            f"[{cal_style}]{cal_status}[/{cal_style}]",
        )

        console.print(table)

        if result.weekly_fpts_ks or result.stat_ks:
            ks_table = Table(title="Distribution KS")
            ks_table.add_column("Position", style="cyan")
            ks_table.add_column("Stat", no_wrap=True)
            ks_table.add_column("KS", justify="right")
            ks_table.add_column("Projected Mean", justify="right")
            ks_table.add_column("Actual Mean", justify="right")
            ks_table.add_column("Mean Delta", justify="right")
            ks_table.add_column("N", justify="right")

            if result.weekly_fpts_ks:
                _add_ks_row(ks_table, "ALL", "fpts", result.weekly_fpts_ks)

            for pos, stat in STAT_KS_DISPLAY_ROWS:
                row = result.stat_ks.get(pos, {}).get(stat)
                if row:
                    _add_ks_row(ks_table, pos, stat, row)

            console.print(ks_table)

        overall = "PASS" if result.passes_targets() else "FAIL"
        overall_style = "green bold" if overall == "PASS" else "red bold"
        console.print(f"\n[{overall_style}]Overall: {overall}[/{overall_style}]")

    return capture.get()
