from pathlib import Path
from typing import Any

from app.ai.llm import create_completion
from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(prompt_name: str) -> str:
    prompt_path = PROMPT_DIR / f"prompt_{prompt_name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def run_prompt(prompt_name: str, context: dict[str, Any]) -> str:
    prompt_text = load_prompt(prompt_name)
    logger.info("Running prompt %s", prompt_name)
    request_text = "\n".join([
        prompt_text,
        "\n\nContext:\n",
        str(context),
    ])
    response = create_completion(
        request_text,
        model=settings.OPENAI_MODEL,
        max_tokens=settings.OPENAI_MAX_TOKENS,
    )
    result = response.get("content")
    if not result:
        raise RuntimeError("LLM returned empty response")
    return result
