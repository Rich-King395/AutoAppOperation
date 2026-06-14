from pathlib import Path

import typer
from rich import print

from appcollector.config import load_configs
from appcollector.errors import AppCollectorError
from appcollector.experiment import ExperimentRun

app = typer.Typer(help="Run AppCollector experiments.")


def _fail(message: str) -> None:
    print(f"[red]Error:[/red] {message}")
    raise typer.Exit(1)


@app.command("validate-config")
def validate_config(config_dir: Path = typer.Option(Path("configs"), help="Config directory.")) -> None:
    """Validate that YAML configs can be loaded."""
    try:
        configs = load_configs(config_dir)
    except AppCollectorError as exc:
        _fail(str(exc))
    else:
        print(f"[green]Loaded configs:[/green] {', '.join(sorted(configs))}")


@app.command()
def smoke(
    experiment_id: str | None = typer.Argument(None, help="Experiment id. Defaults to the first matrix row."),
    config_dir: Path = typer.Option(Path("configs"), help="Config directory."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run without connecting to Appium."),
) -> None:
    """Run the first matrix experiment as a smoke check."""
    try:
        configs = load_configs(config_dir)
        selected = experiment_id or configs["experiment_matrix"]["experiments"][0]["experiment_id"]
        result = ExperimentRun.from_configs(selected, configs).smoke(dry_run=dry_run)
    except AppCollectorError as exc:
        _fail(str(exc))
    else:
        print(result)


@app.command()
def run(
    experiment_id: str = typer.Argument(..., help="Experiment id from experiment_matrix.yaml."),
    config_dir: Path = typer.Option(Path("configs"), help="Config directory."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run without connecting to Appium."),
) -> None:
    """Run one experiment from the matrix."""
    try:
        experiment = ExperimentRun.from_configs(experiment_id, load_configs(config_dir))
        result = experiment.run(dry_run=dry_run)
    except AppCollectorError as exc:
        _fail(str(exc))
    else:
        print(result)


@app.command("run-matrix")
def run_matrix(
    config_dir: Path = typer.Option(Path("configs"), help="Config directory."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run without connecting to Appium."),
) -> None:
    """Run all experiments in experiment_matrix.yaml."""
    try:
        configs = load_configs(config_dir)
        results = []
        for row in configs["experiment_matrix"]["experiments"]:
            results.append(ExperimentRun.from_configs(row["experiment_id"], configs).run(dry_run=dry_run))
    except AppCollectorError as exc:
        _fail(str(exc))
    else:
        print(results)


if __name__ == "__main__":
    app()
