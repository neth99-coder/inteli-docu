import httpx

from app.config import get_settings
from app.services.gemini import (
    ACCOUNTANT_SUMMARY_PROMPT,
    GeminiRateLimitError,
    GeminiServiceError,
    LLM_RATE_LIMIT_MESSAGE,
    LLM_UNAVAILABLE_MESSAGE,
    NO_ACCOUNTING_SUMMARY,
    PAGE_QA_PROMPT,
    build_previous_page_context,
    is_reference_page,
    normalize_page_text,
)


def _build_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    if settings.openrouter_site_url:
        headers["HTTP-Referer"] = settings.openrouter_site_url

    if settings.openrouter_app_name:
        headers["X-Title"] = settings.openrouter_app_name

    return headers


def _extract_message_text(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
        return "\n".join(text_parts)

    return ""


async def call_openrouter(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    models_to_try = [settings.openrouter_model, *settings.openrouter_fallback_models]
    payload_base = {
        "messages": messages,
        "temperature": 0.1,
    }

    last_error: Exception | None = None

    for model_name in models_to_try:
        payload = {
            **payload_base,
            "model": model_name,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=_build_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code in {429, 500, 502, 503, 504}:
                continue
            raise GeminiServiceError(LLM_UNAVAILABLE_MESSAGE) from exc
        except httpx.HTTPError as exc:
            last_error = exc
            continue
    else:
        if isinstance(last_error, httpx.HTTPStatusError) and last_error.response.status_code == 429:
            raise GeminiRateLimitError(LLM_RATE_LIMIT_MESSAGE) from last_error
        raise GeminiServiceError(LLM_UNAVAILABLE_MESSAGE) from last_error

    return _extract_message_text(data)


async def generate_page_summary(
    current_page_text: str,
    previous_page_text: str | None = None,
) -> str:
    if is_reference_page(current_page_text):
        return NO_ACCOUNTING_SUMMARY

    previous_page_context = build_previous_page_context(previous_page_text)
    normalized_current_page = normalize_page_text(current_page_text)
    user_prompt = (
        "Before writing bullets, first decide whether the current page contains substantive body text.\n"
        "If it is mainly a contents page, navigation page, index, or heading list, return the no-information sentence exactly.\n\n"
        f"Previous page context for continuity only:\n{previous_page_context or '[No previous page context]'}\n\n"
        f"Current page to summarize:\n{normalized_current_page or '[No text extracted from this page]'}"
    )
    text = await call_openrouter(
        [
            {"role": "system", "content": ACCOUNTANT_SUMMARY_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    return text or NO_ACCOUNTING_SUMMARY


async def answer_page_question(
    question: str,
    current_page_text: str,
    previous_page_text: str | None = None,
    next_page_text: str | None = None,
) -> str:
    user_prompt = (
        f"User question:\n{question.strip() or '[No question provided]'}\n\n"
        f"Previous page context:\n{previous_page_text or '[No previous page context]'}\n\n"
        f"Current page:\n{current_page_text or '[No text extracted from this page]'}\n\n"
        f"Next page context:\n{next_page_text or '[No next page context]'}"
    )
    text = await call_openrouter(
        [
            {"role": "system", "content": PAGE_QA_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    return text or "The page does not provide enough information to answer that."
