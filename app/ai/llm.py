import os
from typing import Any

import openai

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _load_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for AI prompt execution")
    return api_key


def create_completion(prompt: str, model: str = "gpt-4o-mini", max_tokens: int = 1500) -> dict[str, Any]:
    openai.api_key = _load_api_key()
    logger.info("Calling OpenAI model %s", model)
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful analysis assistant."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
        top_p=0.95,
    )
    return response.choices[0].message.to_dict()
