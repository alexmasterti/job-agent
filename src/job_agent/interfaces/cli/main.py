"""CLI entry point — each verb is a Command class wired via Typer."""

from __future__ import annotations

import typer

from job_agent.interfaces.cli.commands import discover as discover_cmd
from job_agent.interfaces.cli.commands import match as match_cmd
from job_agent.interfaces.cli.commands import profile as profile_cmd

app = typer.Typer(name="job-agent", help="Autonomous job application agent CLI.")

app.add_typer(profile_cmd.app, name="profile")
app.add_typer(discover_cmd.app, name="discover")
app.add_typer(match_cmd.app, name="match")


if __name__ == "__main__":
    app()
