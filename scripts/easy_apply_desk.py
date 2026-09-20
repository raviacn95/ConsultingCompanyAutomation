"""Easy Apply desk — fill (default) or optionally submit no-email queued jobs.

Two people, never mix:
  --user ravi  → kit user ravi, profiles under .browser-profiles/ravi/{site}/
  --user jaya  → kit user jaya, profiles under .browser-profiles/jaya/{site}/

Default is --fill-only (safe). Sites ban bots; CAPTCHA / login stop the run.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from easy_apply_connectors.apply import apply_one, boot_kit_user, ensure_kit_job  # noqa: E402
from easy_apply_connectors.browser import launch_context, profile_dir  # noqa: E402
from easy_apply_connectors.queue import (  # noqa: E402
    append_log,
    load_queued,
    summarize_by_site,
    user_config,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_list(args: argparse.Namespace) -> int:
    jobs = load_queued(
        args.user,
        site=args.site,
        include_other=args.include_other,
        use_all_queued=args.all_queued,
    )
    counts = summarize_by_site(jobs)
    cfg = user_config(args.user)
    print(f"{cfg['label']} ({args.user}) — no-email Easy Apply queue")
    print(f"  queued file: {cfg['queued']}")
    print(f"  log file:    {cfg['log']}")
    print(f"  by site:     {counts or '(none)'}")
    print(f"  total:       {len(jobs)}")
    limit = args.limit or 30
    for job in jobs[:limit]:
        print(f"  [{job.site:8}] {job.id[:12]}  {job.title[:55]}  | {job.company[:30]}")
    if len(jobs) > limit:
        print(f"  … {len(jobs) - limit} more (raise --limit)")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    site = args.site or "indeed"
    if site == "other":
        raise SystemExit("--site must be indeed|linkedin|naukri for login")
    path = profile_dir(args.user, site)
    print(f"Opening Edge profile for {args.user}/{site}")
    print(f"  path: {path}")
    print("  Sign in once in this window, then close it. Session persists for later fills.")
    with launch_context(args.user, site, headless=False) as (_ctx, page):
        print(f"  current URL: {page.url}")
        print("  Press Enter here when you have finished logging in…")
        try:
            input()
        except EOFError:
            page.wait_for_timeout(120_000)
    print("Saved. Next: python scripts/easy_apply_desk.py --user", args.user, "--fill-only --limit 3")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    # --submit wins; --fill-only is the documented default when --submit is absent
    submit = bool(args.submit)
    jobs = load_queued(
        args.user,
        site=args.site,
        include_other=False,
        use_all_queued=args.all_queued,
    )
    if args.site:
        jobs = [j for j in jobs if j.site == args.site]
    limit = max(1, min(args.limit, 100))
    jobs = jobs[:limit]
    if not jobs:
        print("No matching no-email queued jobs (or all already filled/submitted).")
        return 0

    store, create_packet, load_profile, fill_payload, fill_application_page, kit_user = boot_kit_user(
        user_config(args.user)["kit_user"]
    )
    profile = load_profile()
    print(
        f"Active kit user={kit_user} | profile={profile.full_name} | "
        f"mode={'submit' if submit else 'fill-only'} | jobs={len(jobs)}"
    )

    cfg = user_config(args.user)
    by_site: dict[str, list] = defaultdict(list)
    for job in jobs:
        by_site[job.site].append(job)

    stats = defaultdict(int)
    for site, site_jobs in by_site.items():
        print(f"\n=== {site} ({len(site_jobs)}) profile={profile_dir(args.user, site)} ===")
        with launch_context(args.user, site, headless=args.headless) as (_ctx, page):
            for job in site_jobs:
                print(f"→ {job.title[:60]} @ {job.company[:40]}")
                try:
                    kit_job = ensure_kit_job(store, create_packet, job)
                    payload = fill_payload(profile, kit_job)
                    outcome = apply_one(
                        page,
                        user=args.user,
                        job=job,
                        kit_job=kit_job,
                        payload=payload,
                        fill_application_page=fill_application_page,
                        submit=submit,
                    )
                except Exception as exc:  # noqa: BLE001
                    outcome_status = "failed"
                    detail = str(exc)[:400]
                    shot = ""
                    from easy_apply_connectors.apply import ApplyOutcome

                    outcome = ApplyOutcome(outcome_status, detail, shot)

                stats[outcome.status] += 1
                append_log(
                    cfg["log"],
                    {
                        "id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "site": job.site,
                        "url": job.url,
                        "status": outcome.status,
                        "detail": (outcome.detail + (f" | shot={outcome.shot}" if outcome.shot else ""))[:800],
                        "timestamp": utc_now(),
                    },
                )
                print(f"  {outcome.status}: {outcome.detail[:160]}")
                if outcome.status in {"needs_login", "captcha"}:
                    print("  Stopping this site — fix login/CAPTCHA, then re-run.")
                    break
    print("\nDone.", dict(stats))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Indeed / LinkedIn / Naukri Easy Apply desk (fill-only by default)"
    )
    p.add_argument("--user", required=True, choices=["ravi", "jaya"], help="Never mix mailboxes/profiles")
    p.add_argument("--site", choices=["indeed", "linkedin", "naukri", "other"], default=None)
    p.add_argument("--list", action="store_true", help="List no-email queued jobs by site")
    p.add_argument("--login", action="store_true", help="Open persistent Edge profile to sign in once")
    p.add_argument("--fill-only", action="store_true", help="Fill fields; do not click Submit (default if --submit omitted)")
    p.add_argument("--submit", action="store_true", help="Attempt Submit where selectors are stable (risky)")
    p.add_argument("--limit", type=int, default=5, help="Max jobs this run (default 5, hard cap 100)")
    p.add_argument("--include-other", action="store_true", help="Include non Indeed/LinkedIn/Naukri URLs in --list")
    p.add_argument("--all-queued", action="store_true", help="Jaya: also read apply_queued.csv")
    p.add_argument("--headless", action="store_true", help="Headless Edge (usually worse for CAPTCHA)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.list:
        return cmd_list(args)
    if args.login:
        return cmd_login(args)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
