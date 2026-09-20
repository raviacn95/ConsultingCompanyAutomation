"""Fill (and optionally submit) one queued Easy Apply job using job-apply-kit."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

KIT = Path(r"C:\Users\ravir\job-apply-kit")
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from . import indeed, linkedin, naukri
from .browser import shots_dir
from .queue import QueuedJob
from .walls import check_walls

SITE_MODS = {
    "indeed": indeed,
    "linkedin": linkedin,
    "naukri": naukri,
}


@dataclass
class ApplyOutcome:
    status: str
    detail: str
    shot: str = ""


def boot_kit_user(user: str):
    from jobkit.paths import set_active_user
    from jobkit import store
    from jobkit.packet import create_packet
    from jobkit.profile import load_profile
    from jobkit.form_fill import fill_payload, fill_application_page

    name = set_active_user(user)
    profile = load_profile()
    if user == "ravi":
        if "ravi" not in profile.full_name.lower() and "kumar" not in profile.full_name.lower():
            raise SystemExit(f"Active kit profile is not Ravi after set_active_user: {profile.full_name}")
    elif user == "jaya":
        if "jaya" not in profile.full_name.lower():
            raise SystemExit(f"Active kit profile is not Jaya after set_active_user: {profile.full_name}")
    return store, create_packet, load_profile, fill_payload, fill_application_page, name


def ensure_kit_job(store, create_packet, job: QueuedJob):
    existing = store.find_by_url(job.url)
    if existing:
        kit_job = existing
    else:
        jd = (
            f"Title: {job.title}\nCompany: {job.company}\nURL: {job.url}\n\n"
            f"(Queued Easy Apply — packet from title/company; refine via Apply desk if needed.)"
        )
        jid = store.add_job(
            title=job.title or "Untitled",
            company=job.company or "",
            jd_text=jd,
            url=job.url,
            source="easy_apply_queue",
        )
        kit_job = store.get_job(jid)
    needs = not kit_job.resume_path or not Path(kit_job.resume_path).is_file()
    if needs or kit_job.status == "matched":
        create_packet(kit_job.id)
        kit_job = store.get_job(kit_job.id) or kit_job
    return kit_job


def _screenshot(page, user: str, job_id: str, tag: str) -> str:
    path = shots_dir(user) / f"{job_id}_{tag}_{datetime.now(timezone.utc).strftime('%H%M%S')}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:
        return ""


def apply_one(
    page,
    *,
    user: str,
    job: QueuedJob,
    kit_job,
    payload: dict,
    fill_application_page,
    submit: bool,
) -> ApplyOutcome:
    mod = SITE_MODS.get(job.site)
    try:
        page.goto(job.url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
    except Exception as exc:
        shot = _screenshot(page, user, job.id, "nav")
        return ApplyOutcome("failed", f"Navigation failed: {exc}", shot)

    wall = check_walls(page)
    if wall:
        shot = _screenshot(page, user, job.id, wall.kind)
        return ApplyOutcome(wall.kind, wall.detail, shot)

    opened = False
    if mod:
        opened = mod.open_apply(page)
        page.wait_for_timeout(800)
        wall = check_walls(page)
        if wall:
            shot = _screenshot(page, user, job.id, wall.kind)
            return ApplyOutcome(wall.kind, wall.detail, shot)

    # LinkedIn Easy Apply is also opened inside fill_application_page; for other
    # sites we already clicked Apply. Reuse kit filler (never submits).
    result = fill_application_page(page, payload)
    detail_bits = list(result.messages)
    if opened:
        detail_bits.insert(0, f"Opened {job.site} apply UI")
    if result.files:
        detail_bits.append(f"resume attached x{result.files}")
    elif payload.get("resume_path"):
        detail_bits.append(f"resume ready at {payload['resume_path']} (attach manually if site blocked file input)")

    wall = check_walls(page)
    if wall:
        shot = _screenshot(page, user, job.id, wall.kind)
        return ApplyOutcome(wall.kind, "; ".join(detail_bits + [wall.detail]), shot)

    if not submit:
        return ApplyOutcome(
            "filled",
            "; ".join(detail_bits) + " — Submit left for human (fill-only)",
        )

    if not mod:
        return ApplyOutcome("failed", "No submit helpers for site=other")

    # Step through Next a few more times, then attempt Submit
    from jobkit.form_fill import is_advance_control, is_submit_control

    for _ in range(4):
        advanced = False
        for label in ("Next", "Continue", "Review"):
            try:
                loc = page.get_by_role("button", name=label)
                if loc.count() and loc.first.is_visible():
                    text = (loc.first.inner_text() or "").strip()
                    if is_submit_control(text):
                        continue
                    if is_advance_control(text) or label.lower() in {"next", "continue", "review"}:
                        loc.first.click(timeout=2000)
                        page.wait_for_timeout(800)
                        advanced = True
                        break
            except Exception:
                continue
        if not advanced:
            break
        wall = check_walls(page)
        if wall:
            shot = _screenshot(page, user, job.id, wall.kind)
            return ApplyOutcome(wall.kind, "; ".join(detail_bits + [wall.detail]), shot)

    if mod.click_submit(page):
        wall = check_walls(page)
        if wall:
            shot = _screenshot(page, user, job.id, wall.kind)
            return ApplyOutcome(wall.kind, "; ".join(detail_bits + [wall.detail]), shot)
        return ApplyOutcome("submitted", "; ".join(detail_bits + ["Clicked Submit"]))

    shot = _screenshot(page, user, job.id, "submit_miss")
    return ApplyOutcome(
        "filled",
        "; ".join(detail_bits + ["Submit button not found — left filled for human"]),
        shot,
    )
