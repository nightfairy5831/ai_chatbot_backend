import resend
from app.core.config import RESEND_API_KEY, RESEND_FROM_EMAIL


def send_booking_confirmation(
    to_email: str,
    agent_name: str,
    customer_name: str,
    customer_email: str | None,
    customer_phone: str | None,
    date: str,
    time: str,
    notes: str | None = None,
):
    if not RESEND_API_KEY:
        return

    resend.api_key = RESEND_API_KEY

    html = f"""
    <h2>New Appointment Booked</h2>
    <p>Your AI agent <strong>{agent_name}</strong> has booked a new appointment.</p>
    <table style="border-collapse:collapse;margin-top:12px;">
        <tr><td style="padding:6px 12px;font-weight:bold;">Customer</td><td style="padding:6px 12px;">{customer_name}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Date</td><td style="padding:6px 12px;">{date}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Time</td><td style="padding:6px 12px;">{time}</td></tr>
        {"<tr><td style='padding:6px 12px;font-weight:bold;'>Email</td><td style='padding:6px 12px;'>" + customer_email + "</td></tr>" if customer_email else ""}
        {"<tr><td style='padding:6px 12px;font-weight:bold;'>Phone</td><td style='padding:6px 12px;'>" + customer_phone + "</td></tr>" if customer_phone else ""}
        {"<tr><td style='padding:6px 12px;font-weight:bold;'>Notes</td><td style='padding:6px 12px;'>" + notes + "</td></tr>" if notes else ""}
    </table>
    """

    try:
        resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"New Appointment Booked — {agent_name}",
            "html": html,
        })
    except Exception:
        pass
