from twilio.rest import Client
from twilio.request_validator import RequestValidator
from app.core.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

_client = None


def get_client() -> Client:
    global _client
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError("Twilio credentials not configured")
    if _client is None:
        _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _client


def send_whatsapp_message(to: str, body: str, from_number: str) -> str:
    client = get_client()
    message = client.messages.create(
        body=body,
        from_=f"whatsapp:{from_number}",
        to=f"whatsapp:{to}",
    )
    return message.sid


def validate_webhook(url: str, params: dict, signature: str) -> bool:
    if not TWILIO_AUTH_TOKEN:
        return False
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(url, params, signature)


def list_available_numbers(country_code: str = "US", limit: int = 10) -> list[dict]:
    client = get_client()
    numbers = client.available_phone_numbers(country_code).local.list(
        sms_enabled=True,
        limit=limit,
    )
    return [{"phone_number": n.phone_number, "friendly_name": n.friendly_name} for n in numbers]


def buy_number(phone_number: str) -> str:
    client = get_client()
    incoming = client.incoming_phone_numbers.create(phone_number=phone_number)
    return incoming.sid


def release_number(twilio_sid: str) -> bool:
    client = get_client()
    try:
        client.incoming_phone_numbers(twilio_sid).delete()
        return True
    except Exception:
        return False
