"""Easy Apply connectors for Indeed / LinkedIn / Naukri (no-email queue only).

Philosophy matches job-apply-kit: fill forms from the active user's vault/packet;
humans click Submit unless --submit is set. Sites ban bots — expect CAPTCHA and
login walls. Never mix Ravi and Jaya profiles or mailboxes.
"""

from .classify import classify_site, SITE_HOSTS

__all__ = ["classify_site", "SITE_HOSTS"]
