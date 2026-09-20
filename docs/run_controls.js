/**
 * Pages "Run now" — triggers GitHub Actions workflow_dispatch.
 * Token stays in localStorage only; never commit secrets.
 */
(function () {
  const LS_TOKEN = "sap-desk-gh-token";
  const LS_OWNER = "sap-desk-gh-owner";
  const LS_REPO = "sap-desk-gh-repo";
  const LS_WF = "sap-desk-gh-workflow";
  const DEFAULT_WF = "watch-jobs.yml";

  function detectOwnerRepo() {
    const host = location.hostname || "";
    const parts = (location.pathname || "").split("/").filter(Boolean);
    // https://USER.github.io/REPO/...
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

  function actionsUrl(owner, repo) {
    return "https://github.com/" + owner + "/" + repo + "/actions/workflows/" + DEFAULT_WF;
  }

  function apiHeaders(token) {
    return {
      Accept: "application/vnd.github+json",
      Authorization: "Bearer " + token,
      "X-GitHub-Api-Version": "2022-11-28",
    };
  }

  async function dispatch(owner, repo, token, mail) {
    const wf = localStorage.getItem(LS_WF) || DEFAULT_WF;
    const url =
      "https://api.github.com/repos/" +
      owner +
      "/" +
      repo +
      "/actions/workflows/" +
      encodeURIComponent(wf) +
      "/dispatches";
    const body = {
      ref: "main",
      inputs: {
        mail: mail ? "true" : "false",
      },
    };
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

  async function latestRuns(owner, repo, token) {
    const url =
      "https://api.github.com/repos/" +
      owner +
      "/" +
      repo +
      "/actions/workflows/" +
      encodeURIComponent(DEFAULT_WF) +
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
      link.href = actionsUrl(o, r);
      link.hidden = false;
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

  async function refreshRuns() {
    const { owner, repo, token } = saveForm();
    if (!owner || !repo || !token) {
      status("Save owner/repo and a fine-grained or classic PAT (repo + actions) to poll runs.", "muted");
      return;
    }
    try {
      const data = await latestRuns(owner, repo, token);
      const runs = (data && data.workflow_runs) || [];
      if (!runs.length) {
        status("No workflow runs yet for " + DEFAULT_WF, "muted");
        return;
      }
      const top = runs[0];
      status("Last run: " + formatRun(top), top.conclusion === "success" ? "ok" : top.status === "in_progress" || top.status === "queued" ? "running" : "warn");
      const list = el("run-list");
      if (list) {
        list.innerHTML = runs
          .slice(0, 5)
          .map(function (r) {
            return (
              '<li><a href="' +
              r.html_url +
              '" target="_blank" rel="noopener">' +
              formatRun(r) +
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
      await dispatch(owner, repo, token, mail);
      status("Triggered. Polling runs — watch card updates after the self-hosted cycle finishes and pushes docs/.", "ok");
      setTimeout(refreshRuns, 2500);
      setTimeout(refreshRuns, 12000);
    } catch (err) {
      status("Dispatch failed: " + (err && err.message ? err.message : err), "warn");
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
    const pollBtn = el("btn-poll-runs");
    const clearBtn = el("btn-clear-token");
    if (saveBtn) saveBtn.addEventListener("click", function () { saveForm(); status("Saved in localStorage (this browser only).", "ok"); loadForm(); });
    if (runBtn) runBtn.addEventListener("click", function () { runNow(true); });
    if (pollBtn) pollBtn.addEventListener("click", refreshRuns);
    if (clearBtn) clearBtn.addEventListener("click", clearToken);
    if (localStorage.getItem(LS_TOKEN)) refreshRuns();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
