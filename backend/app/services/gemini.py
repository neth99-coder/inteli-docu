import httpx
import re

from app.config import get_settings

NO_ACCOUNTING_SUMMARY = "No significant accounting-relevant information."
LLM_RATE_LIMIT_MESSAGE = (
    "The AI service is temporarily rate-limited. Please wait a moment and try asking again."
)
LLM_UNAVAILABLE_MESSAGE = (
    "The AI service is temporarily unavailable. Please try again shortly."
)

ACCOUNTANT_SUMMARY_PROMPT = """You are an expert tax accountant and financial analyst.

Analyze the following page and extract only relevant information for an accountant.

Focus on:
    • tax rules
    • rates and percentages
    • thresholds and limits
    • deadlines
    • compliance requirements
    • exceptions
    • penalties
    • eligibility criteria
    • filing extensions
    • conditions that change whether filing is required

Important exclusions:
    • table of contents pages
    • index pages
    • section lists
    • navigation pages that mainly list headings and page numbers

If the current page is a table of contents, index, outline, navigation list, or otherwise lacks substantive body text,
say exactly:
'No significant accounting-relevant information.'

Return structured output with bullet points.

Keep it concise:
- maximum 5 bullet points
- each bullet must be one sentence
- each bullet should be under 28 words
- do not repeat the source text
- do not infer rules from headings alone
- prioritize concrete obligations, exemptions, deadlines, extensions, and qualifying conditions over generic background statements
- include separate bullets for materially different deadlines or exceptions on the same page
- do not include introductory or closing remarks"""

PAGE_QA_PROMPT = """You are an expert tax accountant and financial analyst.

Answer the user's question using the current page as the primary source.

Rules:
- prioritize the current page over adjacent context
- use adjacent pages only when they clearly clarify the current page
- if the answer is not supported by the page content, say that the page does not provide enough information
- be precise about dates, filing obligations, thresholds, exceptions, penalties, and conditions
- keep the answer concise but complete
- use short paragraphs or bullet points when helpful
"""


TOC_HEADING_PATTERNS = (
    "table of contents",
    "contents",
    "index",
)


class GeminiServiceError(Exception):
    pass


class GeminiRateLimitError(GeminiServiceError):
    pass


def is_reference_page(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return True

    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return True

    heading_hit = any(pattern in normalized for pattern in TOC_HEADING_PATTERNS)
    short_lines = sum(1 for line in lines if len(line.split()) <= 12)
    numeric_tail_lines = sum(
        1
        for line in lines
        if re.search(r"(?:\.{2,}|\s)\d{1,4}$", line)
    )
    question_listing_lines = sum(
        1
        for line in lines
        if re.match(r"^(question|section|chapter|appendix)\b", line.strip(), re.IGNORECASE)
    )

    if heading_hit and numeric_tail_lines >= 3:
        return True

    if len(lines) >= 6 and numeric_tail_lines >= max(3, len(lines) // 3) and short_lines >= len(lines) // 2:
        return True

    if len(lines) >= 8 and question_listing_lines >= 4 and numeric_tail_lines >= 3:
        return True

    return False


async def call_gemini(prompt: str) -> str:
    settings = get_settings()
    models_to_try = [settings.gemini_model, *settings.gemini_fallback_models]
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ]
    }

    last_error: Exception | None = None

    for model_name in models_to_try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent"
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "x-goog-api-key": settings.gemini_api_key,
                        "Content-Type": "application/json",
                    },
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

    candidates = data.get("candidates", [])
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts", [])
    return "\n".join(part.get("text", "").strip() for part in parts if part.get("text"))


async def generate_page_summary(
    current_page_text: str,
    previous_page_text: str | None = None,
    next_page_text: str | None = None,
) -> str:
    if is_reference_page(current_page_text):
        return NO_ACCOUNTING_SUMMARY

    prompt = (
        f"{ACCOUNTANT_SUMMARY_PROMPT}\n\n"
        "Use adjacent pages only for context.\n"
        "Summarize only the current page.\n\n"
        f"Previous page context:\n{previous_page_text or '[No previous page context]'}\n\n"
        f"Current page:\n{current_page_text or '[No text extracted from this page]'}\n\n"
        f"Next page context:\n{next_page_text or '[No next page context]'}"
    )

    text = await call_gemini(prompt)

    return text or NO_ACCOUNTING_SUMMARY


async def answer_page_question(
    question: str,
    current_page_text: str,
    previous_page_text: str | None = None,
    next_page_text: str | None = None,
) -> str:
    prompt = (
        f"{PAGE_QA_PROMPT}\n\n"
        f"User question:\n{question.strip() or '[No question provided]'}\n\n"
        f"Previous page context:\n{previous_page_text or '[No previous page context]'}\n\n"
        f"Current page:\n{current_page_text or '[No text extracted from this page]'}\n\n"
        f"Next page context:\n{next_page_text or '[No next page context]'}"
    )

    text = await call_gemini(prompt)

    return text or "The page does not provide enough information to answer that."
