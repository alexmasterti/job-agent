"""discover command — fetch jobs from Greenhouse, Lever, or all sources."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from job_agent.composition_root import build_container
from job_agent.config import Settings
from job_agent.logging_config import configure_logging

app = typer.Typer(help="Job discovery commands.")
console = Console()


@app.command("run")
def run(
    user_email: Annotated[str, typer.Option("--user-email", "-u", help="Authenticated user email")],
    source: Annotated[str, typer.Option("--source", "-s", help="greenhouse | lever | all")] = "all",
    keyword: Annotated[
        str, typer.Option("--keyword", "-k", help="Search query (title match)")
    ] = "software engineer",
    remote: Annotated[
        bool, typer.Option("--remote/--no-remote", help="Remote-only filter")
    ] = False,
) -> None:
    """Discover jobs from ATS job boards and persist them to the database."""
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.app_env)
    container = build_container(settings)

    async def _run_async() -> None:
        user = await container.user_repo.get_by_email(user_email.lower())
        if not user:
            console.print(f"[red]No user found for {user_email}. Run: job-agent profile load[/red]")
            raise typer.Exit(1)

        with console.status(f"Discovering '{keyword}' from {source}…"):
            results = await container.discover_jobs.execute(
                user_id=user.id,
                source_name=source,
                query=keyword,
                remote=remote,
            )

        table = Table(title="Discovery Results", show_header=True, header_style="bold cyan")
        table.add_column("Source")
        table.add_column("Fetched", justify="right")
        table.add_column("New", justify="right", style="green")
        table.add_column("Skipped", justify="right", style="dim")

        total_new = 0
        for r in results:
            table.add_row(r.source, str(r.fetched), str(r.new), str(r.skipped))
            total_new += r.new

        console.print(table)
        console.print(
            f"\n[bold green]Done.[/bold green] {total_new} new jobs added to the database."
        )

    asyncio.run(_run_async())
