from app.config import get_settings
from app.services.gemini import (
    GeminiRateLimitError as LlmRateLimitError,
    GeminiServiceError as LlmServiceError,
    NO_ACCOUNTING_SUMMARY,
    is_reference_page,
)
from app.services.gemini import answer_page_question as answer_page_question_with_gemini
from app.services.gemini import generate_page_summary as generate_page_summary_with_gemini
from app.services.openrouter import answer_page_question as answer_page_question_with_openrouter
from app.services.openrouter import generate_page_summary as generate_page_summary_with_openrouter


def _use_openrouter() -> bool:
    return get_settings().llm_provider.strip().lower() == "openrouter"


async def generate_page_summary(
    current_page_text: str,
    previous_page_text: str | None = None,
) -> str:
    if _use_openrouter():
        return await generate_page_summary_with_openrouter(
            current_page_text=current_page_text,
            previous_page_text=previous_page_text,
        )

    return await generate_page_summary_with_gemini(
        current_page_text=current_page_text,
        previous_page_text=previous_page_text,
    )


async def answer_page_question(
    question: str,
    current_page_text: str,
    previous_page_text: str | None = None,
    next_page_text: str | None = None,
) -> str:
    if _use_openrouter():
        return await answer_page_question_with_openrouter(
            question=question,
            current_page_text=current_page_text,
            previous_page_text=previous_page_text,
            next_page_text=next_page_text,
        )

    return await answer_page_question_with_gemini(
        question=question,
        current_page_text=current_page_text,
        previous_page_text=previous_page_text,
        next_page_text=next_page_text,
    )
