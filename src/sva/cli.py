"""Typer CLI -- `sva ingest <clip>`, `sva intake ...`, `sva cost <game_id>`, `sva version`.

Invocation forms:
    python -m sva.cli ingest clip.mp4
    python -m sva.cli intake --url https://www.youtube.com/watch?v=demo --ack-rights --caller-id builder
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
from sva.eval import run_eval
from sva.ingest import ingest_local_file, ingest_remote_url
from sva.pipeline import run_pipeline

app = typer.Typer(
    name="sva",
    help="Sports Video Analytics ingest and pipeline CLI.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
eval_app = typer.Typer(help="Evaluation harness commands.")
app.add_typer(eval_app, name="eval")


@app.command()
def ingest(
    clip: Annotated[Path, typer.Argument(exists=True, readable=True)],
    game_id: Annotated[str | None, typer.Option("--game-id", help="Override the generated game id")] = None,
    model: Annotated[str, typer.Option("--model", help="VLM model id (Phase 1 uses stub regardless)")] = "gemini-2.5-flash",
    fps: Annotated[int, typer.Option("--fps", help="Sampling fps; Phase 1 uses 1")] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print plan without executing")] = False,
) -> None:
    """Run the Phase 1/Phase 2 local clip through the current pipeline entrypoint."""
    console.print(f"[bold]sva ingest[/bold] clip={clip} model={model} fps={fps} dry_run={dry_run}")
    if dry_run:
        console.print("[yellow]--dry-run: no pipeline executed[/yellow]")
        raise typer.Exit(0)

    result = run_pipeline(clip, game_id=game_id, target_fps=fps)

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
def intake(
    clip: Annotated[Path | None, typer.Argument(exists=True, readable=True)] = None,
    url: Annotated[str | None, typer.Option("--url", help="Approved public video URL (YouTube/UFA only)")] = None,
    ack_rights: Annotated[bool, typer.Option("--ack-rights", help="Acknowledge rights for remote URL ingest")] = False,
    caller_id: Annotated[str, typer.Option("--caller-id", help="Caller identifier for rights-ack logging")] = "cli",
    game_id: Annotated[str | None, typer.Option("--game-id", help="Override the generated game id")] = None,
    fps: Annotated[int, typer.Option("--fps", help="Target CFR fps for ingest normalization")] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print plan without executing")] = False,
) -> None:
    """Normalize one local file or approved public URL through the shared ingest service."""
    if (clip is None and url is None) or (clip is not None and url is not None):
        raise typer.BadParameter("Provide exactly one source: either <clip> or --url.")

    console.print(
        f"[bold]sva intake[/bold] clip={clip} url={url} fps={fps} dry_run={dry_run}"
    )
    if dry_run:
        console.print("[yellow]--dry-run: no pipeline executed[/yellow]")
        raise typer.Exit(0)

    if url is not None:
        result = ingest_remote_url(
            url,
            caller_id=caller_id,
            ack_rights=ack_rights,
            game_id=game_id,
            target_fps=fps,
        )
    else:
        assert clip is not None
        result = ingest_local_file(clip, game_id=game_id, target_fps=fps)

    table = Table(title="Ingest Result")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("game_id", result.game_id)
    table.add_row("video_id", result.video_id)
    table.add_row("source_kind", result.source_kind)
    table.add_row("source_url", result.source_url or "-")
    table.add_row("source", result.source_path)
    table.add_row("transcoded", result.transcoded_path)
    table.add_row("duration_s", f"{result.duration_s:.2f}")
    table.add_row("status", result.status)
    table.add_row("window_count", str(len(result.windows)))
    table.add_row("src_vfr", str(result.source_metadata.is_variable_fps))
    table.add_row("transcoded_vfr", str(result.transcoded_metadata.is_variable_fps))
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


@eval_app.command("run")
def eval_run(
    gold_manifest: Annotated[Path, typer.Argument(exists=True, readable=True)],
    predictions: Annotated[
        Path | None,
        typer.Option("--predictions", exists=True, readable=True, help="Optional predicted-events JSON fixture"),
    ] = None,
) -> None:
    """Run the Phase 7 eval harness against a gold manifest."""
    report = run_eval(gold_manifest, predictions_path=predictions)
    console.print_json(data=report.model_dump(mode="json"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
