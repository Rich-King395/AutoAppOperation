from pathlib import Path

from appcollector.config import load_configs
from appcollector.experiment import ExperimentRun


def main() -> None:
    configs = load_configs(Path("configs"))
    for row in configs["experiment_matrix"].get("experiments", []):
        experiment = ExperimentRun.from_configs(row["experiment_id"], configs)
        experiment.run(dry_run=True)


if __name__ == "__main__":
    main()
