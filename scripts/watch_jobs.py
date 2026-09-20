"""Hourly job watch: harvest new roles, Excel newest-first, dashboard refresh, auto-email.

Ravi: remote Tosca / SAP from jobs_worldwide (updated sidecar if Excel is open).
Jaya: Teradata / EDW / Informatica / Hadoop in data/jaya_teradata/.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
LOG = ROOT / "data" / "watch_jobs.log"
LOCK = ROOT / "data" / "watch_jobs.lock"
DASH_JS = ROOT / "dashboard" / "watch.js"
DOCS_WATCH_JS = ROOT / "docs" / "watch.js"
TASK_NAME = "SAPDeskWatchJobs"
DONE_RE = re.compile(r"sent=(\d+).*queued=(\d+).*errors=(\d+)", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(script: str, extra: list[str]) -> tuple[int, str]:
    cmd = [PY, "-u", str(ROOT / "scripts" / script), *extra]
    print(">", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out:
        print(out[-4000:], flush=True)
    return proc.returncode, out


def append_log(text: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def parse_done(line: str) -> dict:
    match = DONE_RE.search(line or "")
    if not match:
        return {"sent": 0, "queued": 0, "errors": 0}
    return {"sent": int(match.group(1)), "queued": int(match.group(2)), "errors": int(match.group(3))}


def person_stats(*, name: str, mailbox: str, track: str, sent_log: Path, queued_log: Path, mail_line: str) -> dict:
    done = parse_done(mail_line)
    queued = csv_rows(queued_log)
    if done["queued"]:
        queued = done["queued"]
    return {
        "name": name,
        "mailbox": mailbox,
        "track": track,
        "sent_cycle": done["sent"],
        "sent_total": csv_rows(sent_log),
        "queued": queued,
        "errors": done["errors"],
        "mail": mail_line or "",
    }


def snapshot(*, running: bool, started: str, finished: str, ok: bool, ravi_mail: str, jaya_mail: str, steps: list) -> dict:
    world = load_json(ROOT / "data" / "jobs_summary.json")
    td = load_json(ROOT / "data" / "jaya_teradata" / "summary.json")
    ravi = person_stats(
        name="Ravi Kumar",
        mailbox="ravik021995@gmail.com",
        track="Tosca / SAP QA",
        sent_log=ROOT / "data" / "ravi_remote_apply_log.csv",
        queued_log=ROOT / "data" / "ravi_remote_apply_queued.csv",
        mail_line=ravi_mail,
    )
    ravi["unique_jobs"] = int(world.get("unique_jobs") or 0)
    ravi["sap_jobs"] = int(world.get("sap_jobs") or 0)
    jaya = person_stats(
        name="Jaya Gupta",
        mailbox="jayagupta20252003@gmail.com",
        track="Teradata / EDW / Informatica",
        sent_log=ROOT / "data" / "jaya_teradata" / "apply_log.csv",
        queued_log=ROOT / "data" / "jaya_teradata" / "apply_remote_queued.csv",
        mail_line=jaya_mail,
    )
    jaya["unique_jobs"] = int(td.get("unique_jobs") or 0)
    jaya["remote_jobs"] = int(td.get("remote_jobs") or 0)
    jaya["with_emails"] = int(td.get("with_emails") or 0)
    return {
        "interval": "hourly",
        "started_at": started,
        "finished_at": finished,
        "running": running,
        "ok": ok,
        "steps": steps,
        "ravi_mail": ravi_mail,
        "jaya_mail": jaya_mail,
        "ravi": ravi,
        "jaya": jaya,
        "worldwide": {
            "unique_jobs": ravi["unique_jobs"],
            "sap_jobs": ravi["sap_jobs"],
            "generated_at": world.get("generated_at") or "",
        },
        "teradata": {
            "unique_jobs": jaya["unique_jobs"],
            "remote_jobs": jaya["remote_jobs"],
            "with_emails": jaya["with_emails"],
            "generated_at": td.get("generated_at") or "",
        },
    }


def write_dashboard(payload: dict) -> None:
    text = "window.WATCH = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    DASH_JS.parent.mkdir(parents=True, exist_ok=True)
    DASH_JS.write_text(text, encoding="utf-8")
    # Keep GitHub Pages source in sync when docs/ exists
    if DOCS_WATCH_JS.parent.is_dir():
        DOCS_WATCH_JS.write_text(text, encoding="utf-8")


def acquire_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            old = int((LOCK.read_text(encoding="utf-8").strip() or "0").split()[0])
        except ValueError:
            old = 0
        if old and _pid_running(old):
            print(f"Watch already running as PID {old}; skip overlap", flush=True)
            return False
    LOCK.write_text(f"{os.getpid()} {utc_now()}\n", encoding="utf-8")
    return True


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
    return str(pid) in (proc.stdout or "")


def release_lock() -> None:
    try:
        if LOCK.exists() and str(os.getpid()) in LOCK.read_text(encoding="utf-8"):
            LOCK.unlink()
    except OSError:
        pass


def one_cycle(*, extra_auto: int, extra_td: int, wanted: int, mail: bool) -> dict:
    if not acquire_lock():
        payload = snapshot(
            running=True,
            started=utc_now(),
            finished="",
            ok=True,
            ravi_mail="skipped: previous cycle still running",
            jaya_mail="skipped: previous cycle still running",
            steps=[],
        )
        write_dashboard(payload)
        return payload

    started = utc_now()
    payload = snapshot(running=True, started=started, finished="", ok=True, ravi_mail="", jaya_mail="", steps=[])
    write_dashboard(payload)
    steps = payload["steps"]

    try:
        code, out = run(
            "harvest_jobs.py",
            ["--focus", "automation", "--extra", str(extra_auto), "--wanted", str(wanted), "--skip-apis"],
        )
        steps.append({"step": "harvest_tosca_sap", "code": code, "tail": out[-500:]})
        if code != 0:
            payload["ok"] = False

        code, out = run("harvest_jobs.py", ["--export-only"])
        steps.append({"step": "export_worldwide_excel", "code": code, "tail": out[-400:]})
        write_dashboard(snapshot(running=True, started=started, finished="", ok=payload["ok"], ravi_mail="", jaya_mail="", steps=steps))

        code, out = run(
            "harvest_teradata.py",
            ["--extra", str(extra_td), "--wanted", str(min(wanted, 40))],
        )
        steps.append({"step": "harvest_teradata", "code": code, "tail": out[-500:]})
        if code != 0:
            payload["ok"] = False
        write_dashboard(snapshot(running=True, started=started, finished="", ok=payload["ok"], ravi_mail="", jaya_mail="", steps=steps))

        ravi_mail = ""
        jaya_mail = ""
        if mail:
            code, out = run("apply_remote_ravi.py", [])
            ravi_mail = next((line for line in out.splitlines() if line.startswith("Done.")), out[-200:])
            steps.append({"step": "mail_ravi", "code": code, "tail": ravi_mail})
            write_dashboard(snapshot(running=True, started=started, finished="", ok=payload["ok"], ravi_mail=ravi_mail, jaya_mail="", steps=steps))
            code, out = run("apply_jaya_teradata.py", ["--remote-only"])
            jaya_mail = next((line for line in out.splitlines() if line.startswith("Done.")), out[-200:])
            steps.append({"step": "mail_jaya", "code": code, "tail": jaya_mail})

        payload = snapshot(
            running=False,
            started=started,
            finished=utc_now(),
            ok=payload["ok"],
            ravi_mail=ravi_mail,
            jaya_mail=jaya_mail,
            steps=steps,
        )
        write_dashboard(payload)
        append_log(f"{started} ok={payload['ok']} ravi={ravi_mail} jaya={jaya_mail}")
        print(json.dumps({k: payload[k] for k in ("started_at", "finished_at", "ok", "ravi_mail", "jaya_mail")}, indent=2))
        return payload
    finally:
        release_lock()


def install_task() -> str:
    launcher = ROOT / "scripts" / "watch_hourly.vbs"
    launcher.write_text(
        "Set sh = CreateObject(\"Wscript.Shell\")\n"
        f'sh.CurrentDirectory = "{ROOT}"\n'
        f'sh.Run """{PY}"" -u ""{ROOT / "scripts" / "watch_jobs.py"}"" --once --mail", 0, True\n',
        encoding="ascii",
    )
    cmd = [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/SC",
        "HOURLY",
        "/MO",
        "1",
        "/TR",
        f'wscript.exe //B "{launcher}"',
        "/F",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    detail = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        raise SystemExit(f"Could not install {TASK_NAME}: {detail}")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}'; "
                "$t.Settings.DisallowStartIfOnBatteries = $false; "
                "$t.Settings.StopIfGoingOnBatteries = $false; "
                "$t.Settings.AllowDemandStart = $true; "
                "Set-ScheduledTask -InputObject $t | Out-Null"
            ),
        ],
        capture_output=True,
        text=True,
    )
    return f"Installed Windows task {TASK_NAME} every 1 hour (hidden). {detail}"


def uninstall_task() -> str:
    proc = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
    if proc.returncode == 0:
        return f"Removed {TASK_NAME}."
    return (proc.stdout or proc.stderr or f"No task {TASK_NAME}").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly harvest + Excel + auto-apply mail for Ravi and Jaya")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit (used by Task Scheduler)")
    parser.add_argument("--mail", action="store_true", help="Email new Ravi Tosca/SAP and Jaya Teradata matches")
    parser.add_argument("--install", action="store_true", help="Register the hourly Windows task")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--extra-auto", type=int, default=250)
    parser.add_argument("--extra-td", type=int, default=120)
    parser.add_argument("--wanted", type=int, default=40)
    args = parser.parse_args()
    if args.uninstall:
        print(uninstall_task())
        return 0
    if args.install:
        print(install_task())
        if not args.once:
            return 0
    one_cycle(extra_auto=args.extra_auto, extra_td=args.extra_td, wanted=args.wanted, mail=args.mail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
