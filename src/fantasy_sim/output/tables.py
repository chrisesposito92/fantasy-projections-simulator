from rich.console import Console
from rich.table import Table


def _render_table(table: Table) -> str:
    """Render a Rich table to a string."""
    console = Console(width=120, force_terminal=True)
    with console.capture() as capture:
        console.print(table)
    return capture.get()


def format_qb_table(projections: list[dict]) -> str:
    table = Table(title="QB Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("PaYd", justify="right")
    table.add_column("PaTD", justify="right")
    table.add_column("INT", justify="right")
    table.add_column("RuYd", justify="right")
    table.add_column("RuTD", justify="right")
    table.add_column("Sck", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['pass_yards']:.0f}", f"{p['pass_tds']:.1f}",
            f"{p['interceptions']:.1f}", f"{p['rush_yards']:.1f}",
            f"{p['rush_tds']:.1f}", f"{p['sacks']:.1f}", f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_rb_table(projections: list[dict]) -> str:
    table = Table(title="RB Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("RuYd", justify="right")
    table.add_column("RuTD", justify="right")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['rush_yards']:.1f}", f"{p['rush_tds']:.1f}",
            f"{p['targets']:.1f}", f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}", f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_wr_table(projections: list[dict]) -> str:
    table = Table(title="WR Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("ReTD", justify="right")
    table.add_column("RuYd", justify="right")
    table.add_column("RuTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['targets']:.1f}", f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}", f"{p['receiving_tds']:.1f}",
            f"{p.get('rush_yards', 0):.1f}", f"{p.get('rush_tds', 0):.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_te_table(projections: list[dict]) -> str:
    """TE table — same columns as WR."""
    table = Table(title="TE Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['targets']:.1f}", f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}", f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_qb_detail_table(projections: list[dict]) -> str:
    """QB table with floor/ceiling/stddev columns."""
    table = Table(title="QB Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("PaYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("PaTD", justify="right")
    table.add_column("INT", justify="right")
    table.add_column("RuYd", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['pass_yards']:.0f}",
            f"{p.get('pass_yards_floor', 0):.0f}",
            f"{p.get('pass_yards_ceiling', 0):.0f}",
            f"{p['pass_tds']:.1f}",
            f"{p['interceptions']:.1f}",
            f"{p.get('rush_yards', 0):.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_rb_detail_table(projections: list[dict]) -> str:
    """RB table with floor/ceiling/stddev columns."""
    table = Table(title="RB Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("RuYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("RuTD", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['rush_yards']:.1f}",
            f"{p.get('rush_yards_floor', 0):.1f}",
            f"{p.get('rush_yards_ceiling', 0):.1f}",
            f"{p['rush_tds']:.1f}",
            f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_wr_detail_table(projections: list[dict]) -> str:
    """WR table with floor/ceiling/stddev columns."""
    table = Table(title="WR Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['targets']:.1f}",
            f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}",
            f"{p.get('receiving_yards_floor', 0):.1f}",
            f"{p.get('receiving_yards_ceiling', 0):.1f}",
            f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_te_detail_table(projections: list[dict]) -> str:
    """TE table with floor/ceiling/stddev columns."""
    table = Table(title="TE Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['targets']:.1f}",
            f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}",
            f"{p.get('receiving_yards_floor', 0):.1f}",
            f"{p.get('receiving_yards_ceiling', 0):.1f}",
            f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_kicker_table(projections: list[dict]) -> str:
    table = Table(title="K Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("FGA", justify="right")
    table.add_column("FGM", justify="right")
    table.add_column("FG50+", justify="right")
    table.add_column("XPA", justify="right")
    table.add_column("XPM", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['fg_attempts']:.1f}", f"{p['fg_made']:.1f}",
            f"{p['fg_50_plus']:.1f}", f"{p['xp_attempts']:.1f}", f"{p['xp_made']:.1f}",
        )

    return _render_table(table)


def format_dst_table(projections: list[dict]) -> str:
    table = Table(title="DST Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Team", style="cyan")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Sck", justify="right")
    table.add_column("INT", justify="right")
    table.add_column("FR", justify="right")
    table.add_column("DTD", justify="right")
    table.add_column("Saf", justify="right")
    table.add_column("PtsAllow", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["team"],
            f"{p['fpts']:.1f}", f"{p['sacks']:.1f}", f"{p['interceptions']:.1f}",
            f"{p['fumble_recoveries']:.1f}", f"{p['dst_tds']:.1f}",
            f"{p['safeties']:.1f}", f"{p['points_allowed']:.1f}",
        )

    return _render_table(table)
