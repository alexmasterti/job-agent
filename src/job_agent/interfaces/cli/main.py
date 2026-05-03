"""CLI entry point — each verb is a Command class wired via Typer."""

from __future__ import annotations

import typer

from job_agent.interfaces.cli.commands import profile as profile_cmd

app = typer.Typer(name="job-agent", help="Autonomous job application agent CLI.")

app.add_typer(profile_cmd.app, name="profile")


if __name__ == "__main__":
    app()
