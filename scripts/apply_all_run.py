"""Apply-all orchestrator for GitHub Actions / Pages "Apply all".

Runs email apply (Ravi + Jaya) and/or Easy Apply desk with optional --submit.
Writes dashboard/apply_all_status.js (mirrored to docs by the workflow).
Never mixes Ravi and Jaya profiles or mailboxes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable
STATUS_PATH = ROOT / "dashboard" / "apply_all_status.js"
PROFILES = ROOT / ".browser-profiles"
SITES = ("indeed", "linkedin", "naukri")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(payload: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = "window.APPLY_ALL_STATUS = " + json.dumps(payload, indent=2) + ";\n"
    STATUS_PATH.write_text(body, encoding="utf-8")
    # Keep a JSON copy for local debugging
    (ROOT / "data" / "apply_all_status.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def profile_ready(user: str, site: str) -> tuple[bool, str]:
    """Heuristic: persistent Edge profile must exist with more than an empty shell."""
    path = PROFILES / user / site
    if not path.is_dir():
        return False, f"missing profile dir {path}"
    # Chromium/Edge persistent contexts create Default/ or similar after first launch
    children = list(path.iterdir())
    if not children:
        return False, f"empty profile {path} — run: python scripts/easy_apply_desk.py --user {user} --login --site {site}"
    # Prefer Default + Cookies / Network as a stronger signal
    default = path / "Default"
    if default.is_dir():
        cookies = default / "Network" / "Cookies"
        cookies_alt = default / "Cookies"
        if cookies.exists() or cookies_alt.exists() or any(default.iterdir()):
            return True, "ok"
        return False, f"profile {path} has Default/ but no session data — log in again"
    # Some launches only create Preferences / Local State before full Default
    names = {c.name.lower() for c in children}
    if "local state" in names or "preferences" in names or "default" in names:
        return True, "ok (partial)"
    return False, f"profile {path} looks uninitialized — run --login"


def preflight_easy(users: list[str]) -> dict:
    """Return needs_login map; does not open a browser (avoids CAPTCHA hang)."""
    by_user: dict[str, dict] = {}
    any_ready = False
    needs_login = False
    for user in users:
        sites: dict[str, dict] = {}
        user_ok = False
        for site in SITES:
            ok, detail = profile_ready(user, site)
            sites[site] = {"ready": ok, "detail": detail}
            if ok:
                user_ok = True
                any_ready = True
            else:
                needs_login = True
        by_user[user] = {"any_site_ready": user_ok, "sites": sites}
    return {
        "any_ready": any_ready,
        "needs_login": needs_login and not any_ready,
        "users": by_user,
    }


def run_step(name: str, script: str, argv: list[str], *, timeout_sec: int) -> dict:
    cmd = [PY, "-u", str(SCRIPTS / script), *argv]
    print(f"\n=== {name} ===", flush=True)
    print(" ", " ".join(cmd), flush=True)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = "\n".join(out.splitlines()[-40:])
        print(tail, flush=True)
        return {
            "step": name,
            "code": proc.returncode,
            "tail": tail[-2500:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if exc.stdout:
            partial += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
        if exc.stderr:
            partial += "\n" + (exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace"))
        tail = "\n".join(partial.strip().splitlines()[-40:])
        print(f"TIMEOUT after {timeout_sec}s", flush=True)
        if tail:
            print(tail, flush=True)
        return {
            "step": name,
            "code": 124,
            "tail": (tail or f"timed out after {timeout_sec}s")[-2500:],
            "timed_out": True,
        }


def parse_users(raw: str) -> list[str]:
    v = (raw or "both").strip().lower()
    if v == "ravi":
        return ["ravi"]
    if v == "jaya":
        return ["jaya"]
    return ["ravi", "jaya"]


def main() -> int:
    p = argparse.ArgumentParser(description="Apply-all: mail + Easy Apply (capped)")
    p.add_argument("--mail", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--easy-apply", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--easy-submit", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--easy-limit", type=int, default=50, help="Max Easy Apply jobs per user (hard cap 100)")
    p.add_argument("--user", choices=["both", "ravi", "jaya"], default="both")
    p.add_argument("--mail-timeout", type=int, default=1800)
    p.add_argument("--easy-timeout", type=int, default=3600)
    args = p.parse_args()

    users = parse_users(args.user)
    limit = max(1, min(int(args.easy_limit or 50), 100))
    started = utc_now()
    steps: list[dict] = []
    status = {
        "state": "running",
        "started_at": started,
        "finished_at": None,
        "mail": bool(args.mail),
        "easy_apply": bool(args.easy_apply),
        "easy_submit": bool(args.easy_submit),
        "easy_limit": limit,
        "users": users,
        "preflight": None,
        "steps": steps,
        "summary": "",
        "needs_login": False,
        "ok": False,
    }
    write_status(status)
    print(
        f"Apply-all start users={users} mail={args.mail} easy={args.easy_apply} "
        f"submit={args.easy_submit} limit={limit}",
        flush=True,
    )

    exit_code = 0

    if args.mail:
        if "ravi" in users:
            steps.append(run_step("mail_ravi", "apply_remote_ravi.py", [], timeout_sec=args.mail_timeout))
            if steps[-1]["code"] not in (0,):
                exit_code = max(exit_code, steps[-1]["code"] or 1)
            write_status(status)
        if "jaya" in users:
            steps.append(
                run_step(
                    "mail_jaya",
                    "apply_jaya_teradata.py",
                    ["--remote-only"],
                    timeout_sec=args.mail_timeout,
                )
            )
            if steps[-1]["code"] not in (0,):
                exit_code = max(exit_code, steps[-1]["code"] or 1)
            write_status(status)

    if args.easy_apply:
        pre = preflight_easy(users)
        status["preflight"] = pre
        write_status(status)
        if pre["needs_login"]:
            status["needs_login"] = True
            status["state"] = "needs_login"
            status["summary"] = (
                "Easy Apply skipped: no logged-in browser profiles under .browser-profiles/. "
                "On the runner PC run: python scripts/easy_apply_desk.py --user ravi --login --site indeed "
                "(and linkedin/naukri; same for jaya). Leave PC on; runner sapdesk-windows online."
            )
            status["finished_at"] = utc_now()
            status["ok"] = False
            write_status(status)
            print(status["summary"], flush=True)
            # Soft-fail: mail may have succeeded; exit 2 so Actions shows failure for login
            return 2 if not args.mail else 2

        for who in users:
            user_pf = (pre.get("users") or {}).get(who) or {}
            if not user_pf.get("any_site_ready"):
                steps.append(
                    {
                        "step": f"easy_apply_{who}",
                        "code": 2,
                        "tail": f"needs_login for {who} — no ready site profiles",
                        "timed_out": False,
                        "skipped": True,
                    }
                )
                status["needs_login"] = True
                exit_code = max(exit_code, 2)
                write_status(status)
                continue

            argv = ["--user", who, "--limit", str(limit)]
            if args.easy_submit:
                argv.append("--submit")
            else:
                argv.append("--fill-only")
            step = run_step(
                f"easy_apply_{who}",
                "easy_apply_desk.py",
                argv,
                timeout_sec=args.easy_timeout,
            )
            steps.append(step)
            tail_l = (step.get("tail") or "").lower()
            if "needs_login" in tail_l or step.get("code") == 2:
                status["needs_login"] = True
            if "captcha" in tail_l:
                status["summary"] = (status.get("summary") or "") + f" CAPTCHA hit for {who}; site stopped."
            if step["code"] not in (0,):
                exit_code = max(exit_code, step["code"] or 1)
            if step.get("timed_out"):
                exit_code = max(exit_code, 124)
            write_status(status)

    # Summarize
    ok_steps = sum(1 for s in steps if s.get("code") == 0 and not s.get("skipped"))
    fail_steps = [s["step"] for s in steps if s.get("code") not in (0,) or s.get("skipped")]
    parts = [
        f"users={','.join(users)}",
        f"mail={'on' if args.mail else 'off'}",
        f"easy={'submit' if args.easy_submit else 'fill-only' if args.easy_apply else 'off'}",
        f"limit={limit}",
        f"ok_steps={ok_steps}/{len(steps)}",
    ]
    if status.get("needs_login"):
        parts.append("needs_login=true")
    if fail_steps:
        parts.append("failed=" + ",".join(fail_steps))
    status["summary"] = (status.get("summary") or "").strip() + (" " if status.get("summary") else "") + "; ".join(parts)
    status["finished_at"] = utc_now()
    if status.get("needs_login") and exit_code == 0:
        exit_code = 2
    status["ok"] = exit_code == 0
    status["state"] = "needs_login" if status.get("needs_login") else ("ok" if status["ok"] else "failed")
    write_status(status)

    print("\n=== Apply-all summary ===", flush=True)
    print(status["summary"], flush=True)
    print(f"state={status['state']} exit={exit_code}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
