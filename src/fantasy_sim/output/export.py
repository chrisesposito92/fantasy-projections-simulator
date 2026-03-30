import csv
import json
from pathlib import Path


def export_csv(projections: list[dict], output_path: Path) -> None:
    """Export projections to CSV file."""
    output_path = Path(output_path)
    if not projections:
        output_path.write_text("")
        return

    fieldnames = list(projections[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(projections)


def export_json(projections: list[dict], output_path: Path) -> None:
    """Export projections to JSON file."""
    output_path = Path(output_path)
    with open(output_path, "w") as f:
        json.dump(projections, f, indent=2)
