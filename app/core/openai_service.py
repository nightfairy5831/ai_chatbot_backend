import logging
from openai import OpenAI
from app.core.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def chat_completion(system_prompt: str, user_message: str) -> dict:
    if not client:
        raise ValueError("OpenAI API key is not configured")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
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
