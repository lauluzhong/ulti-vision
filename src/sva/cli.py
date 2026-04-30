"""Typer CLI -- `sva ingest`, `sva intake`, `sva run-local`, `sva cost`, `sva version`, `sva eval`.

v0 smoke flow:
    sva run-local tests/fixtures/cfr_baseline.mp4
    sva run-local --url https://www.youtube.com/watch?v=demo --ack-rights

Other forms:
    sva ingest clip.mp4 --game-id game_abc --fps 1
    sva intake --url https://www.youtube.com/watch?v=demo --ack-rights --caller-id builder
    sva cost game_abc
    sva eval run gold.json
    sva version
"""

from __future__ import annotations

from collections import Counter
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
from sva.events_dao import list_event_rows
from sva.ingest import ingest_local_file, ingest_remote_url
from sva.pipeline import run_pipeline
from sva.points.dao import list_points

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


@app.command("run-local")
def run_local(
    source: Annotated[
        str,
        typer.Argument(help="Local clip path OR a public URL (YouTube/UFA) — use --url for the URL form."),
    ],
    url_mode: Annotated[
        bool,
        typer.Option("--url", help="Treat the source as a public URL instead of a local path."),
    ] = False,
    ack_rights: Annotated[
        bool,
        typer.Option("--ack-rights", help="Required when --url is set: acknowledges rights for remote ingest."),
    ] = False,
    caller_id: Annotated[
        str,
        typer.Option("--caller-id", help="Caller identifier for rights-ack logging (URL mode only)."),
    ] = "cli-smoke",
    game_id: Annotated[str | None, typer.Option("--game-id", help="Override the generated game id")] = None,
    fps: Annotated[int, typer.Option("--fps", help="Sampling fps (1-3 for v0)")] = 1,
) -> None:
    """v0 end-to-end smoke run: ingest -> perceive -> detect points -> interpret -> print summary.

    Useful for testing prompt changes against a real clip without spinning up
    Docker, the API, the queue, or the frontend. Requires GEMINI_API_KEY,
    ANTHROPIC_API_KEY, and a reachable Postgres (DATABASE_URL).
    """
    if url_mode:
        console.print(f"[bold]sva run-local[/bold] [URL mode] url={source} fps={fps}")
        ingest = ingest_remote_url(
            source,
            caller_id=caller_id,
            ack_rights=ack_rights,
            game_id=game_id,
            target_fps=fps,
        )
        clip_path = Path(ingest.transcoded_path)
        effective_game_id = ingest.game_id
        result = run_pipeline(clip_path, game_id=effective_game_id, target_fps=fps)
    else:
        clip_path = Path(source)
        if not clip_path.exists():
            console.print(f"[red]Clip not found: {clip_path}[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]sva run-local[/bold] [local mode] clip={clip_path} fps={fps}")
        result = run_pipeline(clip_path, game_id=game_id, target_fps=fps)

    # ----- High-level result -----
    summary = Table(title="Pipeline Result")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("game_id", result.game_id)
    summary.add_row("video_id", result.video_id)
    summary.add_row("duration_s", f"{result.duration_s:.2f}")
    summary.add_row("windows_processed", str(result.windows_processed))
    summary.add_row("observations", str(result.observations))
    summary.add_row("events_inserted", str(result.events_inserted))
    summary.add_row("total_cost_usd", f"${result.total_cost_usd:.6f}")
    console.print(summary)

    # ----- Detected points -----
    points = list_points(result.game_id)
    points_table = Table(title=f"Detected Points ({len(points)})")
    points_table.add_column("ord")
    points_table.add_column("point_id")
    points_table.add_column("start_ms", justify="right")
    points_table.add_column("end_ms", justify="right")
    points_table.add_column("dur_s", justify="right")
    points_table.add_column("conf", justify="right")
    points_table.add_column("evidence")
    for point in points:
        sources = ",".join(sorted({signal.source for signal in point.boundary_evidence})) or "-"
        duration_s = (point.end_video_ts_ms - point.start_video_ts_ms) / 1000.0
        points_table.add_row(
            str(point.point_ordinal),
            point.point_id,
            str(point.start_video_ts_ms),
            str(point.end_video_ts_ms),
            f"{duration_s:.1f}",
            f"{point.confidence:.2f}",
            sources,
        )
    console.print(points_table)

    # ----- v0 stats: counts of points / turnovers / passes / goals -----
    events = list_event_rows(result.game_id)
    type_counts: Counter[str] = Counter(row.type for row in events)
    stats_table = Table(title="v0 Statistics")
    stats_table.add_column("Metric")
    stats_table.add_column("Count", justify="right")
    stats_table.add_row("Points detected", str(len(points)))
    stats_table.add_row("Goals", str(type_counts.get("goal", 0)))
    stats_table.add_row("Completions (passes)", str(type_counts.get("completion", 0)))
    stats_table.add_row("Turnovers", str(type_counts.get("turnover", 0)))
    stats_table.add_row("Possession transitions", str(
        type_counts.get("possession_start", 0) + type_counts.get("possession_end", 0)
    ))
    stats_table.add_row("Other / unknown", str(
        sum(c for t, c in type_counts.items() if t not in {
            "goal", "completion", "turnover", "possession_start", "possession_end"
        })
    ))
    console.print(stats_table)

    # ----- Honesty banner -----
    if any(point.confidence < 0.3 for point in points):
        console.print(
            "[yellow]NOTE: at least one detected point has confidence < 0.3 — "
            "the VLM didn't give confident phase signals. Consider editing point "
            "boundaries via the alpha UI before trusting the per-point breakdown.[/yellow]"
        )
    if not events:
        console.print(
            "[yellow]NOTE: 0 events emitted. Either the clip has no Ultimate-specific "
            "activity in the windows we sampled, or the prompts need tuning. Open "
            "Langfuse and inspect the perceive traces to see what the VLM actually saw.[/yellow]"
        )


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
