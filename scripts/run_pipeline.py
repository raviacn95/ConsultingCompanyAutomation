"""One command: export harvest → build outreach pipeline → refresh the desk."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(script: str, extra: list[str] | None = None) -> None:
    cmd = [PY, "-u", str(ROOT / "scripts" / script), *(extra or [])]
    print(">", " ".join(cmd))
    try:
        subprocess.check_call(cmd, cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        if script == "harvest_jobs.py" and "--export-only" in (extra or []):
            print("Harvest export skipped (file may be open). Using existing sap_jobs.csv")
            return
        raise exc


def main() -> None:
    parser = argparse.ArgumentParser(description="SAP Desk end-to-end pipeline")
    parser.add_argument("--harvest", action="store_true", help="Also pull new jobs before building")
    parser.add_argument("--target", type=int, default=16000)
    args = parser.parse_args()
    if args.harvest:
        run("harvest_jobs.py", ["--target", str(args.target), "--wanted", "200", "--skip-apis"])
    else:
        run("harvest_jobs.py", ["--export-only"])
    run("build_pipeline.py")
    run("find_sap_leads.py")
    print("Pipeline ready. Open dashboard/index.html")
    print("  python scripts/queue_outreach.py   fill sender + open Gmail for verified To:")
    print("  data/jobs_worldwide.csv  worldwide jobs")
    print("  data/sap_jobs.csv        SAP-tagged jobs")
    print("  data/pipeline.csv        send/later companies with copy")
    print("  dashboard/index.html     curated + harvest desk")


if __name__ == "__main__":
    main()
