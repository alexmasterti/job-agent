"""match command — score jobs against profile and display top matches."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from job_agent.composition_root import build_container
from job_agent.config import Settings
from job_agent.logging_config import configure_logging

app = typer.Typer(help="Job matching commands.")
console = Console()


@app.command("run")
def run(
    user_email: Annotated[str, typer.Option("--user-email", "-u")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max jobs to score")] = 500,
    top: Annotated[int, typer.Option("--top", help="Top N matches to display")] = 20,
) -> None:
    """Score unmatched jobs against the user profile and show top matches."""
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.app_env)
    container = build_container(settings)

    async def _run_async() -> None:
        user = await container.user_repo.get_by_email(user_email.lower())
        if not user:
            console.print(f"[red]No user found for {user_email}[/red]")
            raise typer.Exit(1)

        console.print(f"[cyan]Scoring jobs for {user_email}...[/cyan]")
        console.print("[dim]Loading embedding model (downloads ~1.3 GB on first run)...[/dim]")

        result = await container.match_jobs.execute(user_id=user.id, limit=limit)

        console.print(
            f"\nScored [green]{result.scored}[/green] | "
            f"Saved [green]{result.saved}[/green] | "
            f"Filtered [yellow]{result.filtered}[/yellow] | "
            f"Low-embedding [dim]{result.skipped_low_embedding}[/dim]\n"
        )

        rows = await container.match_repo.list_top(user.id, limit=top)
        if not rows:
            console.print("[yellow]No matches yet.[/yellow]")
            return

        table = Table(title=f"Top {top} Matches", show_header=True, header_style="bold cyan")
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Title", min_width=30)
        table.add_column("Company", min_width=18)
        table.add_column("Location", min_width=16)
        table.add_column("Reasoning")

        for i, (match, title, company, location, _url, _remote) in enumerate(rows, 1):
            score_style = (
                "green"
                if match.final_score >= 70
                else "yellow"
                if match.final_score >= 50
                else "dim"
            )
            table.add_row(
                str(i),
                f"[{score_style}]{match.final_score:.0f}[/{score_style}]",
                title,
                company,
                location or "—",
                match.reasoning[:80] + "..." if len(match.reasoning) > 80 else match.reasoning,
            )

        console.print(table)

    asyncio.run(_run_async())


@app.command("top")
def top_cmd(
    user_email: Annotated[str, typer.Option("--user-email", "-u")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    min_score: Annotated[float, typer.Option("--min-score")] = 0.0,
) -> None:
    """Show top matches already in the database (no re-scoring)."""
    settings = Settings()  # type: ignore[call-arg]
    container = build_container(settings)

    async def _run_async() -> None:
        user = await container.user_repo.get_by_email(user_email.lower())
        if not user:
            console.print(f"[red]No user found for {user_email}[/red]")
            raise typer.Exit(1)

        all_rows = await container.match_repo.list_top(user.id, limit=limit)
        rows = [r for r in all_rows if r[0].final_score >= min_score]

        if not rows:
            console.print("[yellow]No matches found. Run: job-agent match run[/yellow]")
            return

        table = Table(title=f"Top {limit} Matches", show_header=True, header_style="bold cyan")
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Emb", justify="right", width=5, style="dim")
        table.add_column("LLM", justify="right", width=5, style="dim")
        table.add_column("Title", min_width=28)
        table.add_column("Company", min_width=16)
        table.add_column("Location", min_width=14)
        table.add_column("Reasoning")

        for i, (match, title, company, location, _url, _remote) in enumerate(rows, 1):
            score_style = (
                "green"
                if match.final_score >= 70
                else "yellow"
                if match.final_score >= 50
                else "dim"
            )
            table.add_row(
                str(i),
                f"[{score_style}]{match.final_score:.0f}[/{score_style}]",
                f"{match.embedding_score * 100:.0f}",
                f"{match.llm_score:.0f}",
                title,
                company,
                location or "—",
                match.reasoning[:70] + "..." if len(match.reasoning) > 70 else match.reasoning,
            )

        console.print(table)
        if rows:
            console.print(f"\n[dim]URL for #1: {rows[0][4]}[/dim]")

    asyncio.run(_run_async())
