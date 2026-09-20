/**
 * Pages controls — "Run now" (Watch jobs) + "Apply all" (mail + Easy Apply).
 * Token stays in localStorage only; never commit secrets.
 */
(function () {
  const LS_TOKEN = "sap-desk-gh-token";
  const LS_OWNER = "sap-desk-gh-owner";
  const LS_REPO = "sap-desk-gh-repo";
  const LS_WF = "sap-desk-gh-workflow";
  const LS_APPLY_WARN = "sap-desk-apply-all-warned";
  const DEFAULT_WF = "watch-jobs.yml";
  const APPLY_WF = "apply-all.yml";

  function detectOwnerRepo() {
    const host = location.hostname || "";
    const parts = (location.pathname || "").split("/").filter(Boolean);
    if (host.endsWith(".github.io") && parts.length >= 1) {
      const owner = host.replace(".github.io", "");
      return { owner: owner, repo: parts[0] };
    }
    return {
      owner: localStorage.getItem(LS_OWNER) || "",
      repo: localStorage.getItem(LS_REPO) || "",
    };
  }

  function el(id) {
    return document.getElementById(id);
  }

  function status(msg, kind) {
    const box = el("run-status");
    if (!box) return;
    box.textContent = msg;
    box.className = "run-status" + (kind ? " " + kind : "");
  }

  function actionsUrl(owner, repo, wf) {
    return "https://github.com/" + owner + "/" + repo + "/actions/workflows/" + (wf || DEFAULT_WF);
  }

  function apiHeaders(token) {
    return {
      Accept: "application/vnd.github+json",
      Authorization: "Bearer " + token,
      "X-GitHub-Api-Version": "2022-11-28",
    };
  }

  async function dispatchWorkflow(owner, repo, token, workflowFile, inputs) {
    const url =
      "https://api.github.com/repos/" +
      owner +
      "/" +
      repo +
      "/actions/workflows/" +
      encodeURIComponent(workflowFile) +
      "/dispatches";
    const body = { ref: "main", inputs: inputs || {} };
    const res = await fetch(url, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, apiHeaders(token)),
      body: JSON.stringify(body),
    });
    if (res.status === 204) return;
    let detail = res.status + " " + res.statusText;
    try {
      const j = await res.json();
      if (j && j.message) detail += " — " + j.message;
    } catch (_) {}
    throw new Error(detail);
  }

  async function latestRuns(owner, repo, token, workflowFile) {
    const url =
      "https://api.github.com/repos/" +
      owner +
      "/" +
      repo +
      "/actions/workflows/" +
      encodeURIComponent(workflowFile || DEFAULT_WF) +
      "/runs?per_page=5";
    const res = await fetch(url, { headers: apiHeaders(token) });
    if (!res.ok) throw new Error("runs " + res.status);
    return res.json();
  }

  function formatRun(run) {
    const when = run.updated_at || run.created_at || "";
    const concl = run.conclusion || run.status || "";
    return "#" + run.run_number + " " + concl + " · " + when;
  }

  function loadForm() {
    const detected = detectOwnerRepo();
    const ownerEl = el("gh-owner");
    const repoEl = el("gh-repo");
    const tokenEl = el("gh-token");
    if (ownerEl) ownerEl.value = localStorage.getItem(LS_OWNER) || detected.owner || "";
    if (repoEl) repoEl.value = localStorage.getItem(LS_REPO) || detected.repo || "";
    if (tokenEl) tokenEl.value = localStorage.getItem(LS_TOKEN) || "";
    const link = el("gh-actions-link");
    const o = (ownerEl && ownerEl.value) || detected.owner;
    const r = (repoEl && repoEl.value) || detected.repo;
    if (link && o && r) {
      link.href = actionsUrl(o, r, DEFAULT_WF);
      link.hidden = false;
    }
    const applyLink = el("gh-apply-all-link");
    if (applyLink && o && r) {
      applyLink.href = actionsUrl(o, r, APPLY_WF);
      applyLink.hidden = false;
    }
  }

  function saveForm() {
    const owner = (el("gh-owner") && el("gh-owner").value.trim()) || "";
    const repo = (el("gh-repo") && el("gh-repo").value.trim()) || "";
    const token = (el("gh-token") && el("gh-token").value.trim()) || "";
    if (owner) localStorage.setItem(LS_OWNER, owner);
    if (repo) localStorage.setItem(LS_REPO, repo);
    if (token) localStorage.setItem(LS_TOKEN, token);
    else localStorage.removeItem(LS_TOKEN);
    return { owner, repo, token };
  }

  function applyStatusLine() {
    const s = window.APPLY_ALL_STATUS;
    if (!s || typeof s !== "object") return "";
    const bits = [];
    if (s.state) bits.push("state=" + s.state);
    if (s.finished_at) bits.push("finished " + s.finished_at);
    else if (s.started_at) bits.push("started " + s.started_at);
    if (s.needs_login) bits.push("needs_login");
    if (s.easy_limit != null) bits.push("limit=" + s.easy_limit);
    if (s.summary) bits.push(String(s.summary).slice(0, 180));
    return bits.join(" · ");
  }

  async function refreshRuns() {
    const { owner, repo, token } = saveForm();
    if (!owner || !repo || !token) {
      status("Save owner/repo and a fine-grained or classic PAT (repo + actions) to poll runs.", "muted");
      return;
    }
    try {
      const [watchData, applyData] = await Promise.all([
        latestRuns(owner, repo, token, DEFAULT_WF),
        latestRuns(owner, repo, token, APPLY_WF).catch(function () {
          return { workflow_runs: [] };
        }),
      ]);
      const watchRuns = (watchData && watchData.workflow_runs) || [];
      const applyRuns = (applyData && applyData.workflow_runs) || [];
      const topWatch = watchRuns[0];
      const topApply = applyRuns[0];

      let kind = "muted";
      let msg = "";
      const pageStatus = applyStatusLine();
      if (topApply && (topApply.status === "in_progress" || topApply.status === "queued")) {
        kind = "running";
        msg = "Apply all: " + formatRun(topApply);
      } else if (topApply && topApply.conclusion === "failure") {
        kind = "warn";
        msg = "Apply all: " + formatRun(topApply);
      } else if (topApply && topApply.conclusion === "success") {
        kind = "ok";
        msg = "Apply all: " + formatRun(topApply);
      } else if (topWatch) {
        kind =
          topWatch.conclusion === "success"
            ? "ok"
            : topWatch.status === "in_progress" || topWatch.status === "queued"
              ? "running"
              : "warn";
        msg = "Watch: " + formatRun(topWatch);
      } else {
        msg = "No workflow runs yet.";
      }
      if (pageStatus) msg += " | Pages status: " + pageStatus;
      status(msg, kind);

      const list = el("run-list");
      if (list) {
        const merged = []
          .concat(
            applyRuns.slice(0, 3).map(function (r) {
              return { label: "Apply all " + formatRun(r), url: r.html_url };
            })
          )
          .concat(
            watchRuns.slice(0, 3).map(function (r) {
              return { label: "Watch " + formatRun(r), url: r.html_url };
            })
          );
        list.innerHTML = merged
          .map(function (item) {
            return (
              '<li><a href="' +
              item.url +
              '" target="_blank" rel="noopener">' +
              item.label +
              "</a></li>"
            );
          })
          .join("");
      }
    } catch (err) {
      status("Could not load runs: " + (err && err.message ? err.message : err), "warn");
    }
  }

  async function runNow(mail) {
    const { owner, repo, token } = saveForm();
    if (!owner || !repo) {
      status("Set GitHub owner and repo first.", "warn");
      return;
    }
    if (!token) {
      status("Paste a PAT once (stored only in this browser), or use the Actions link below.", "warn");
      return;
    }
    const btn = el("btn-run-now");
    if (btn) btn.disabled = true;
    status("Dispatching Watch jobs…", "running");
    try {
      const wf = localStorage.getItem(LS_WF) || DEFAULT_WF;
      await dispatchWorkflow(owner, repo, token, wf, {
        mail: mail ? "true" : "false",
      });
      status(
        "Triggered Watch jobs. Polling — harvest + mail; dashboard updates after the runner pushes docs/.",
        "ok"
      );
      setTimeout(refreshRuns, 2500);
      setTimeout(refreshRuns, 12000);
    } catch (err) {
      status("Dispatch failed: " + (err && err.message ? err.message : err), "warn");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function confirmApplyAllOnce() {
    if (localStorage.getItem(LS_APPLY_WARN) === "1") return true;
    const ok = window.confirm(
      "Apply all will email-apply queued jobs AND Easy-Apply-submit Indeed/LinkedIn/Naukri no-email rows (up to the per-user limit).\n\n" +
        "Leave this PC on, keep the sapdesk-windows runner online, and ensure .browser-profiles are logged in for each user/site.\n\n" +
        "Continue?"
    );
    if (ok) localStorage.setItem(LS_APPLY_WARN, "1");
    return ok;
  }

  async function applyAll() {
    const { owner, repo, token } = saveForm();
    if (!owner || !repo) {
      status("Set GitHub owner and repo first.", "warn");
      return;
    }
    if (!token) {
      status("Paste a PAT once (stored only in this browser), or open Apply all in Actions.", "warn");
      return;
    }
    if (!confirmApplyAllOnce()) {
      status("Apply all cancelled.", "muted");
      return;
    }
    const btn = el("btn-apply-all");
    if (btn) btn.disabled = true;
    status("Dispatching Apply all (mail + Easy Apply submit)…", "running");
    try {
      await dispatchWorkflow(owner, repo, token, APPLY_WF, {
        mail: "true",
        easy_apply: "true",
        easy_submit: "true",
        easy_limit: "50",
        user: "both",
      });
      status(
        "Triggered Apply all. Polling Actions + apply_all_status.js — up to 50 Easy Apply jobs per user.",
        "ok"
      );
      setTimeout(refreshRuns, 2500);
      setTimeout(refreshRuns, 15000);
      setTimeout(refreshRuns, 45000);
    } catch (err) {
      status("Apply all dispatch failed: " + (err && err.message ? err.message : err), "warn");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function clearToken() {
    localStorage.removeItem(LS_TOKEN);
    if (el("gh-token")) el("gh-token").value = "";
    status("Token cleared from this browser.", "muted");
  }

  function init() {
    if (!el("run-panel")) return;
    loadForm();
    const saveBtn = el("btn-save-gh");
    const runBtn = el("btn-run-now");
    const applyBtn = el("btn-apply-all");
    const pollBtn = el("btn-poll-runs");
    const clearBtn = el("btn-clear-token");
    if (saveBtn)
      saveBtn.addEventListener("click", function () {
        saveForm();
        status("Saved in localStorage (this browser only).", "ok");
        loadForm();
      });
    if (runBtn) runBtn.addEventListener("click", function () {
      runNow(true);
    });
    if (applyBtn) applyBtn.addEventListener("click", applyAll);
    if (pollBtn) pollBtn.addEventListener("click", refreshRuns);
    if (clearBtn) clearBtn.addEventListener("click", clearToken);
    if (localStorage.getItem(LS_TOKEN)) refreshRuns();
    else if (window.APPLY_ALL_STATUS) {
      const line = applyStatusLine();
      if (line) status("Last Apply all on Pages: " + line, window.APPLY_ALL_STATUS.ok ? "ok" : "muted");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
