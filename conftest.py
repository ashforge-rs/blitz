"""
pytest plugin — renders a Rich coverage table after the test session.

Replaces the default coverage-py terminal output with a compact, colour-coded
table.  Enable by running pytest with --cov (pytest-cov handles data
collection; this plugin handles the display).
"""

from __future__ import annotations

import os

import pytest


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
    """Hook called after the full test run.  Renders the coverage table."""
    try:
        import coverage
        from rich import box
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        return

    cov_data = coverage.CoverageData()
    cov_file = os.environ.get("COVERAGE_FILE", ".coverage")
    if not os.path.exists(cov_file):
        return

    cov_data.read()

    cov = coverage.Coverage(data_file=cov_file)
    cov.load()

    console = Console()
    console.print()

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        title="[bold white]Coverage Report[/bold white]",
        title_justify="left",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("Module", style="white", no_wrap=True)
    table.add_column("Stmts", justify="right", style="dim white")
    table.add_column("Miss", justify="right")
    table.add_column("Cover", justify="right")
    table.add_column("Missing lines", style="dim yellow", no_wrap=False)

    total_stmts = 0
    total_miss = 0

    try:
        analysis_results = []
        for fr in cov_data.measured_files():
            try:
                analysis = cov._analyze(fr)
                analysis_results.append((fr, analysis))
            except Exception:
                continue

        # Sort by coverage % ascending (worst first)
        analysis_results.sort(key=lambda x: x[1].numbers.pc_covered)

        for fr, analysis in analysis_results:
            nums = analysis.numbers
            stmts = nums.n_statements
            miss = nums.n_missing
            pct = nums.pc_covered

            total_stmts += stmts
            total_miss += miss

            # Colour the percentage
            if pct >= 90:
                pct_style = "bold green"
            elif pct >= 70:
                pct_style = "yellow"
            else:
                pct_style = "bold red"

            # Shorten path: strip src/ prefix for readability
            display = fr
            for prefix in ("src/", "/home/phoenix/blitz/src/"):
                if display.startswith(prefix):
                    display = display[len(prefix) :]
                    break
            display = display.replace(".py", "")

            missing = ", ".join(str(l) for l in sorted(analysis.missing))  # noqa: E741

            table.add_row(
                display,
                str(stmts),
                Text(str(miss), style="red" if miss else "dim white"),
                Text(f"{pct:.0f}%", style=pct_style),
                missing or "—",
            )

        # Totals row
        total_pct = ((total_stmts - total_miss) / total_stmts * 100) if total_stmts else 0.0
        pct_style = "bold green" if total_pct >= 90 else "yellow" if total_pct >= 70 else "bold red"
        table.add_section()
        table.add_row(
            "[bold white]TOTAL[/bold white]",
            f"[bold]{total_stmts}[/bold]",
            Text(f"[bold]{total_miss}[/bold]", style="red" if total_miss else "green"),
            Text(f"{total_pct:.0f}%", style=pct_style),
            "",
        )

        console.print(table)
        console.print()
    except Exception as exc:
        console.print(f"[dim]Coverage display error: {exc}[/dim]")
