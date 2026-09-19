import argparse
from pathlib import Path

from h1b_job_insights import activity_features, activity_train, pipeline
from h1b_job_insights.activity_data import quarter_number
from h1b_job_insights.company_activity import quarter_label


def run(raw_dir: Path, processed_dir: Path, model_dir: Path, jobs: int = 4) -> dict:
    pipeline.run(raw_dir, processed_dir)
    manifest = activity_features.run(processed_dir)
    activity_train.run(processed_dir / "activity", model_dir, jobs)
    latest = manifest["last_quarter"]
    target = quarter_label(quarter_number(latest) + 1)
    print(f"History through {latest}; target {target}", flush=True)
    return {"trained_through": latest, "target_quarter": target}


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Excel files and retrain filing models")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--model-dir", type=Path, default=Path("artifacts/activity"))
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    run(args.raw_dir, args.processed_dir, args.model_dir, args.jobs)


if __name__ == "__main__":
    main()
