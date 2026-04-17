import json
import logging
from openai import OpenAI
from app.core.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

BOOKING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available time slots on a specific date",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for the customer",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "time": {"type": "string", "description": "Time in HH:MM format"},
                    "customer_name": {"type": "string", "description": "Customer name"},
                    "customer_email": {"type": "string", "description": "Customer email (optional)"},
                    "customer_phone": {"type": "string", "description": "Customer phone (optional)"},
                    "notes": {"type": "string", "description": "Additional notes (optional)"},
                },
                "required": ["date", "time", "customer_name"],
            },
        },
    },
]


def chat_completion(system_prompt: str, user_message: str, history: list[dict] = None) -> dict:
    if not client:
        raise ValueError("OpenAI API key is not configured")

    try:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1024,
        )
        usage = response.usage
        return {
            "content": response.choices[0].message.content,
            "token": usage.total_tokens if usage else 0,
        }
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise


def chat_completion_with_tools(system_prompt: str, user_message: str, tool_handler=None, history: list[dict] = None) -> dict:
    if not client:
        raise ValueError("OpenAI API key is not configured")

    try:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=BOOKING_TOOLS,
            max_tokens=1024,
        )

        message = response.choices[0].message
        total_tokens = response.usage.total_tokens if response.usage else 0

        if message.tool_calls and tool_handler:
            messages.append(message)

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                result = tool_handler(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

            follow_up = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=1024,
            )
            total_tokens += follow_up.usage.total_tokens if follow_up.usage else 0
            return {
                "content": follow_up.choices[0].message.content,
                "token": total_tokens,
            }

        return {
            "content": message.content,
            "token": total_tokens,
        }
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise
