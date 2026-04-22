"""Typer CLI -- `sva ingest <clip>`, `sva cost <game_id>`, `sva version`.

Invocation forms:
    python -m sva.cli ingest clip.mp4
    python -m sva.cli ingest clip.mp4 --game-id game_abc --model gemini-2.5-flash --fps 1
    sva ingest clip.mp4
    sva cost game_abc
    sva version
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from sva import __version__
from sva.db import get_engine
from sva.pipeline import run_pipeline

app = typer.Typer(
    name="sva",
    help="Sports Video Analytics -- Phase 1 narrow vertical slice CLI.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def ingest(
    clip: Annotated[Path, typer.Argument(exists=True, readable=True)],
    game_id: Annotated[str | None, typer.Option("--game-id", help="Override the generated game id")] = None,
    model: Annotated[str, typer.Option("--model", help="VLM model id (Phase 1 uses stub regardless)")] = "gemini-2.5-flash",
    fps: Annotated[int, typer.Option("--fps", help="Sampling fps; Phase 1 uses 1")] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print plan without executing")] = False,
) -> None:
    """Ingest one local clip through the Phase 1 vertical slice."""
    console.print(f"[bold]sva ingest[/bold] clip={clip} model={model} fps={fps} dry_run={dry_run}")
    if dry_run:
        console.print("[yellow]--dry-run: no pipeline executed[/yellow]")
        raise typer.Exit(0)

    result = run_pipeline(clip, game_id=game_id)

    table = Table(title="Pipeline Result")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("game_id", result.game_id)
    table.add_row("video_id", result.video_id)
    table.add_row("source", result.ingest.source_path)
    table.add_row("transcoded", result.ingest.transcoded_path)
    table.add_row("duration_s", f"{result.duration_s:.2f}")
    table.add_row("windows", str(result.windows_processed))
    table.add_row("observations", str(result.observations))
    table.add_row("events_inserted", str(result.events_inserted))
    table.add_row("total_cost_usd", f"${result.total_cost_usd:.6f}")
    table.add_row("src_vfr", str(result.ingest.source_metadata.is_variable_fps))
    table.add_row("transcoded_vfr", str(result.ingest.transcoded_metadata.is_variable_fps))
    console.print(table)


@app.command()
def cost(game_id: Annotated[str, typer.Argument(help="game_id to aggregate cost for")]) -> None:
    """Print aggregated cost_usd for a game (OBS-01)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()
    if row is None:
        console.print(f"[red]No job found for game_id={game_id}[/red]")
        raise typer.Exit(1)
    console.print(f"game_id={game_id} cost_usd=${Decimal(row):.6f}")


@app.command()
def version() -> None:
    """Print sva package version."""
    console.print(f"sva {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
