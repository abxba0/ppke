"""Email delivery via Resend.

Set ``RESEND_API_KEY`` in ``~/.ppke/.env`` or the environment to enable
email sending.  When the key is absent every send call is a no-op so the
rest of the application works without it.

An optional ``RESEND_FROM_EMAIL`` (default ``PPKE <noreply@ppke.app>``)
controls the sender address — make sure the domain is verified in Resend.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy Resend initialisation
# ---------------------------------------------------------------------------
_resend_ready: Optional[bool] = None


def _ensure_resend() -> bool:
    """Initialise the Resend SDK once.  Returns *True* when ready."""
    global _resend_ready
    if _resend_ready is not None:
        return _resend_ready

    # Load .env so RESEND_API_KEY can live in ~/.ppke/.env
    try:
        from ppke.config import _load_env_file
        env_vars = _load_env_file()
        for k, v in env_vars.items():
            os.environ.setdefault(k, v)
    except Exception:
        pass

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.info("RESEND_API_KEY not set — email delivery disabled")
        _resend_ready = False
        return False

    try:
        import resend
        resend.api_key = api_key
        _resend_ready = True
        logger.info("Resend email delivery enabled")
        return True
    except ImportError:
        logger.warning("resend package not installed — pip install resend")
        _resend_ready = False
        return False


def _from_address() -> str:
    return os.environ.get("RESEND_FROM_EMAIL", "PPKE <noreply@ppke.app>")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def send_invite_email(
    *,
    to_email: str,
    inviter_name: str,
    workspace_name: str,
    role: str,
    invite_url: str,
) -> bool:
    """Send a workspace invitation email.

    Returns ``True`` if the email was queued successfully, ``False`` otherwise
    (including when Resend is not configured).
    """
    if not _ensure_resend():
        return False

    import resend

    subject = f"You're invited to join \"{workspace_name}\" on PPKE"

    html = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 520px; margin: 0 auto; padding: 32px 0;">
  <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border-radius: 16px 16px 0 0; padding: 32px; text-align: center;">
    <h1 style="color: #fff; margin: 0; font-size: 22px; font-weight: 700;">You're Invited!</h1>
  </div>
  <div style="background: #ffffff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 16px 16px; padding: 32px;">
    <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px;">
      <strong>{inviter_name}</strong> has invited you to join the workspace
      <strong>&ldquo;{workspace_name}&rdquo;</strong> as a <strong>{role}</strong>.
    </p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{invite_url}"
         style="display: inline-block; background: #6366f1; color: #ffffff; padding: 14px 36px;
                border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 15px;">
        Accept Invitation
      </a>
    </div>
    <p style="color: #6b7280; font-size: 13px; line-height: 1.5; margin: 0;">
      If the button doesn't work, copy and paste this link into your browser:<br>
      <a href="{invite_url}" style="color: #6366f1; word-break: break-all;">{invite_url}</a>
    </p>
    <hr style="border: none; border-top: 1px solid #f3f4f6; margin: 24px 0;">
    <p style="color: #9ca3af; font-size: 12px; margin: 0; text-align: center;">
      This invitation will expire in 7 days.
      If you didn't expect this email you can safely ignore it.
    </p>
  </div>
</div>"""

    text = (
        f"{inviter_name} invited you to join \"{workspace_name}\" as {role}.\n\n"
        f"Accept the invitation: {invite_url}\n\n"
        "This link expires in 7 days."
    )

    try:
        params: resend.Emails.SendParams = {
            "from": _from_address(),
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        }
        result = resend.Emails.send(params)
        logger.info("Invite email sent to %s (id=%s)", to_email, result.get("id"))
        return True
    except Exception as exc:
        logger.error("Failed to send invite email to %s: %s", to_email, exc)
        return False


def send_generic_email(
    *,
    to_email: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> bool:
    """Send an arbitrary email.  Returns ``True`` on success."""
    if not _ensure_resend():
        return False

    import resend

    try:
        params: resend.Emails.SendParams = {
            "from": _from_address(),
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text
        resend.Emails.send(params)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False
