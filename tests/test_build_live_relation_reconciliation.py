import gzip
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts/build_live_relation_reconciliation.py"
TRACKED_INVENTORY = (
    REPO_ROOT
    / "artifacts/reports/t_8c7f0862/relation_reconciliation_live_t_8c7f0862_gcs_inventory.json.gz"
)


def raw_item(identity: dict[str, object]) -> dict[str, dict[str, object]]:
    bucket, name = str(identity["uri"]).removeprefix("gs://").split("/", 1)
    return {
        "metadata": {
            "bucket": bucket,
            "name": name,
            "generation": identity["generation"],
            "size": identity["size_bytes"],
            "md5Hash": identity["md5_base64"],
            "crc32c": identity["crc32c_base64"],
            "updated": identity["updated"],
        }
    }


def test_symmetric_inventory_truncation_fails_before_writing_outputs(tmp_path: Path) -> None:
    tracked = json.loads(gzip.decompress(TRACKED_INVENTORY.read_bytes()))
    inventory_dir = tmp_path / "inventory"
    inventory_dir.mkdir()
    for area, identities in tracked["inventories"].items():
        items = [raw_item(identity) for identity in identities]
        for suffix in ("", "_end"):
            (inventory_dir / f"{area}{suffix}.json").write_text(json.dumps(items))

    removed_names = []
    for filename in ("staging.json", "staging_end.json"):
        items = json.loads((inventory_dir / filename).read_text())
        victim = next(
            item
            for item in items
            if item["metadata"]["name"].endswith(".parquet.sha256")
            and "remap" in item["metadata"]["name"].lower()
        )
        removed_names.append(victim["metadata"]["name"])
        truncated = [item for item in items if item is not victim]
        (inventory_dir / filename).write_text(json.dumps(truncated))

    assert removed_names[0] == removed_names[1]
    outputs = {
        "json": tmp_path / "accepted-ledger.json",
        "markdown": tmp_path / "accepted-report.md",
        "inventory": tmp_path / "accepted-inventory.json",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--inventory-dir",
            str(inventory_dir),
            "--captured-at",
            tracked["captured_at"],
            "--schema-commit",
            "034e498abb54d6d98e1b2b86f4a50b2b51f893f5",
            "--json-output",
            str(outputs["json"]),
            "--markdown-output",
            str(outputs["markdown"]),
            "--inventory-output",
            str(outputs["inventory"]),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, result.stdout
    assert "staging" in result.stderr
    assert "completeness" in result.stderr
    assert all(not path.exists() for path in outputs.values())
