window.APPLY_ALL_STATUS = {
  "state": "needs_login",
  "started_at": "2026-09-20T20:03:52Z",
  "finished_at": "2026-09-20T20:03:56Z",
  "mail": true,
  "easy_apply": true,
  "easy_submit": false,
  "easy_limit": 5,
  "users": [
    "ravi",
    "jaya"
  ],
  "preflight": {
    "any_ready": false,
    "needs_login": true,
    "users": {
      "ravi": {
        "any_site_ready": false,
        "sites": {
          "indeed": {
            "ready": false,
            "detail": "empty profile C:\\Users\\ravir\\ConsultingCompanyAutomation\\.browser-profiles\\ravi\\indeed \u2014 run: python scripts/easy_apply_desk.py --user ravi --login --site indeed"
          },
          "linkedin": {
            "ready": false,
            "detail": "missing profile dir C:\\Users\\ravir\\ConsultingCompanyAutomation\\.browser-profiles\\ravi\\linkedin"
          },
          "naukri": {
            "ready": false,
            "detail": "missing profile dir C:\\Users\\ravir\\ConsultingCompanyAutomation\\.browser-profiles\\ravi\\naukri"
          }
        }
      },
      "jaya": {
        "any_site_ready": false,
        "sites": {
          "indeed": {
            "ready": false,
            "detail": "missing profile dir C:\\Users\\ravir\\ConsultingCompanyAutomation\\.browser-profiles\\jaya\\indeed"
          },
          "linkedin": {
            "ready": false,
            "detail": "missing profile dir C:\\Users\\ravir\\ConsultingCompanyAutomation\\.browser-profiles\\jaya\\linkedin"
          },
          "naukri": {
            "ready": false,
            "detail": "missing profile dir C:\\Users\\ravir\\ConsultingCompanyAutomation\\.browser-profiles\\jaya\\naukri"
          }
        }
      }
    }
  },
  "steps": [
    {
      "step": "mail_ravi",
      "code": 0,
      "tail": "Active user ravi | from ravik021995@gmail.com | JD-tailored packets | source jobs_worldwide.csv | remote SAP/Playwright rows 276\nDone. sent=0 queued=276 errors=0 log=ravi_remote_apply_log.csv queued_log=ravi_remote_apply_queued.csv",
      "timed_out": false
    },
    {
      "step": "mail_jaya",
      "code": 0,
      "tail": "Active user jaya | from jayagupta20252003@gmail.com | rows 54 | log C:\\Users\\ravir\\ConsultingCompanyAutomation\\data\\jaya_teradata\\apply_log.csv\nERROR Staff Software Engineer, Data Warehouse Foundation: Greenhouse 401: HTTP Basic: Access denied.\n\nDone. sent=0 queued=54 errors=1 log=C:\\Users\\ravir\\ConsultingCompanyAutomation\\data\\jaya_teradata\\apply_log.csv queued=C:\\Users\\ravir\\ConsultingCompanyAutomation\\data\\jaya_teradata\\apply_remote_queued.csv",
      "timed_out": false
    },
    {
      "step": "sync_auto_applied",
      "code": 0,
      "tail": "Wrote 169 auto-applied jobs (ravi=144 jaya=25; before_cap=169) -> auto_applied_jobs.js",
      "timed_out": false
    }
  ],
  "summary": "Easy Apply skipped: no logged-in browser profiles under .browser-profiles/. On the runner PC run: python scripts/easy_apply_desk.py --user ravi --login --site indeed (and linkedin/naukri; same for jaya). Leave PC on; runner sapdesk-windows online.",
  "needs_login": true,
  "ok": true
};
