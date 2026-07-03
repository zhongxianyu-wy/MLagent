"""mlagent CLI (Typer).

Deterministic operations live here; workflow judgment lives in the skills.
v0.3 slice-1 skeleton: only `version` for now; subsequent tasks add
init/status/record-raw/distill/convert-to-sop/approve-sop/list-sops/get-sop/
retrain/assemble-context/sync/ui.
"""

import typer

from mlagent import __version__
from mlagent.errors import MlagentError

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _callback() -> None:
    """mlagent — project-level ML modeling memory (raw/experience/Skill-SOP) + R&D asset visualization."""


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo(f"mlagent {__version__}")


def main() -> None:
    try:
        app()
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
