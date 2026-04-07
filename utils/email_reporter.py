"""
Email Reporter
يرسل تقرير أسبوعي للمطور
يخليه يحب الأداة ويدفع بسهولة
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@cryptoapifixer.com")


def build_weekly_report(report: Dict[str, Any]) -> str:
    agent_id = report.get("agent_id", "unknown")
    total_fixes = report.get("total_fixes", 0)
    success_rate = report.get("success_rate", 0)
    avg_latency = report.get("avg_latency_ms", 0)
    estimated_saved = report.get("estimated_losses_prevented_usd", 0)
    top_errors = report.get("top_errors_fixed", [])

    top_errors_text = "\n".join(
        "   - {}".format(e) for e in top_errors
    ) if top_errors else "   - No errors this week"

    return """
=====================================
Crypto API Fixer - Weekly Report
=====================================

Bot ID: {agent_id}
Period: Last 7 days

This Week Your Bot:

   Fixed {total_fixes} API errors automatically
   Success rate: {success_rate}%
   Avg fix time: {avg_latency}ms
   Estimated losses prevented: ${estimated_saved}

Top errors fixed:
{top_errors}

=====================================
Your bot never stopped trading.
We fixed it silently in the background.
=====================================

Powered by Crypto API Fixer
https://cryptoapifixer.com
""".format(
        agent_id=agent_id,
        total_fixes=total_fixes,
        success_rate=success_rate,
        avg_latency=avg_latency,
        estimated_saved=estimated_saved,
        top_errors=top_errors_text,
    )


def send_weekly_report(to_email: str, report: Dict[str, Any]) -> bool:
    try:
        if not SMTP_USER or not SMTP_PASS:
            print("📧 [DEV MODE] Email to: {}".format(to_email))
            print(build_weekly_report(report))
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your Bot Fixed {} Errors This Week".format(
            report.get("total_fixes", 0))
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        msg.attach(MIMEText(build_weekly_report(report), "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())

        return True

    except Exception as e:
        print("Email error: {}".format(str(e)))
        return False


def send_reports_to_all(agent_emails: Dict[str, str]) -> Dict[str, Any]:
    from training.archive_db import get_agent_weekly_report
    results = {"sent": 0, "failed": 0}
    for agent_id, email in agent_emails.items():
        report = get_agent_weekly_report(agent_id)
        if send_weekly_report(email, report):
            results["sent"] += 1
        else:
            results["failed"] += 1
    return results
