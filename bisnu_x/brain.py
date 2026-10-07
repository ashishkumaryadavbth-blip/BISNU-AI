from __future__ import annotations

import re
from typing import Any

from bisnu_x.config import settings
from bisnu_x.inference import model_manager


CREATOR_PHRASES = {
    "english":
        "I was created by YADAV BROTHERS.",
    "hindi":
        "मुझे YADAV BROTHERS ने बनाया है।",
    "hinglish":
        "Mujhe YADAV BROTHERS ne banaya hai.",
    "bengali":
        "আমাকে YADAV BROTHERS তৈরি করেছে।",
    "marathi":
        "मला YADAV BROTHERS यांनी बनवले आहे.",
    "gujarati":
        "મને YADAV BROTHERS એ બનાવ્યો છે.",
    "punjabi":
        "ਮੈਨੂੰ YADAV BROTHERS ਨੇ ਬਣਾਇਆ ਹੈ।",
    "tamil":
        "என்னை YADAV BROTHERS உருவாக்கியுள்ளனர்.",
    "telugu":
        "నన్ను YADAV BROTHERS రూపొందించారు.",
    "kannada":
        "ನನ್ನನ್ನು YADAV BROTHERS ರಚಿಸಿದ್ದಾರೆ.",
    "malayalam":
        "എന്നെ YADAV BROTHERS ആണ് നിർമ്മിച്ചത്.",
    "odia":
        "ମୋତେ YADAV BROTHERS ତିଆରି କରିଛନ୍ତି।",
    "nepali":
        "मलाई YADAV BROTHERS ले बनाएका हुन्।",
    "urdu":
        "مجھے YADAV BROTHERS نے بنایا ہے۔",
    "spanish":
        "Fui creado por YADAV BROTHERS.",
    "french":
        "J’ai été créé par YADAV BROTHERS.",
    "german":
        "Ich wurde von YADAV BROTHERS entwickelt.",
    "portuguese":
        "Fui criado por YADAV BROTHERS.",
    "arabic":
        "لقد أنشأني YADAV BROTHERS.",
    "russian":
        "Меня создали YADAV BROTHERS."
}


def detect_language(text: str):
    value = text.lower().strip()

    # Devanagari
    if re.search(
        r"[\u0900-\u097F]",
        value
    ):
        return "hindi"

    # Bengali
    if re.search(
        r"[\u0980-\u09FF]",
        value
    ):
        return "bengali"

    # Gurmukhi
    if re.search(
        r"[\u0A00-\u0A7F]",
        value
    ):
        return "punjabi"

    # Gujarati
    if re.search(
        r"[\u0A80-\u0AFF]",
        value
    ):
        return "gujarati"

    # Tamil
    if re.search(
        r"[\u0B80-\u0BFF]",
        value
    ):
        return "tamil"

    # Telugu
    if re.search(
        r"[\u0C00-\u0C7F]",
        value
    ):
        return "telugu"

    # Kannada
    if re.search(
        r"[\u0C80-\u0CFF]",
        value
    ):
        return "kannada"

    # Malayalam
    if re.search(
        r"[\u0D00-\u0D7F]",
        value
    ):
        return "malayalam"

    # Odia
    if re.search(
        r"[\u0B00-\u0B7F]",
        value
    ):
        return "odia"

    # Arabic / Urdu
    if re.search(
        r"[\u0600-\u06FF]",
        value
    ):
        return "urdu"

    # Russian/Cyrillic
    if re.search(
        r"[\u0400-\u04FF]",
        value
    ):
        return "russian"

    # Latin-language heuristics
    spanish = [
        "quien",
        "quién",
        "creado",
        "creaste",
        "quien te hizo"
    ]

    french = [
        "qui t'a créé",
        "qui t a créé",
        "créé par"
    ]

    german = [
        "wer hat dich gemacht",
        "wer hat dich erstellt"
    ]

    portuguese = [
        "quem criou você",
        "quem te criou",
        "criado por"
    ]

    arabic_words = [
        "من صنعك",
        "من أنشأك",
        "من طورك"
    ]

    if any(x in value for x in spanish):
        return "spanish"

    if any(x in value for x in french):
        return "french"

    if any(x in value for x in german):
        return "german"

    if any(x in value for x in portuguese):
        return "portuguese"

    if any(x in value for x in arabic_words):
        return "arabic"

    # Hinglish
    hinglish_words = [
        "kisne",
        "banaya",
        "banaya hai",
        "tumhe kisne",
        "aapko kisne",
        "who made you",
        "who created you"
    ]

    if any(
        word in value
        for word in hinglish_words
    ):
        return "hinglish"

    return "english"


def is_creator_question(text: str):
    value = text.lower().strip()

    patterns = [
        "who made you",
        "who created you",
        "who built you",
        "who developed you",
        "who is your creator",
        "who are your creators",
        "who owns you",
        "who made this ai",
        "who made this",
        "kisne banaya",
        "kisne tumhe banaya",
        "tumhe kisne banaya",
        "aapko kisne banaya",
        "tumko kisne banaya",
        "tumhe kisne create kiya",
        "aapko kisne create kiya",
        "तुम्हें किसने बनाया",
        "तुमको किसने बनाया",
        "आपको किसने बनाया",
        "किसने बनाया",
        "तुम्हारा निर्माता कौन",
        "तुम्हें किसने बनाया है",
        "من صنعك",
        "من أنشأك",
        "quem criou você",
        "quien te creó",
        "quién te creó"
    ]

    return any(
        p in value
        for p in patterns
    )


def creator_answer(text: str):
    language = detect_language(
        text
    )

    return CREATOR_PHRASES.get(
        language,
        CREATOR_PHRASES["english"]
    )


BASE_SYSTEM = """
You are BISNU-X, an AI system created by YADAV BROTHERS.

IMPORTANT IDENTITY RULE:
If the user asks who created, made, built, developed,
or is behind you, the factual answer is:
YADAV BROTHERS.

Answer in the same language as the user.

Do not claim that YADAV BROTHERS personally trained
every underlying open-weight model. BISNU-X is the
AI platform/system integrating its configured models.

Be helpful, accurate and honest.
Do not invent facts.
When current information is supplied by search sources,
use those sources carefully.

You are BISNU-X, not ChatGPT, not OpenAI,
not Meta and not Qwen.
"""


def build_context(
    sources: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
    memories: list[dict[str, Any]] | None = None,
):
    if not sources and not history and not memories:
        return ""

    lines = []

    if history:
        lines.append("\nRECENT CONVERSATION (oldest first):\n")
        for item in history[-12:]:
            role = item.get("role", "user")
            content = item.get("content", "")[:4000]
            lines.append(f"{role}: {content}\n")

    if memories:
        lines.append("\nUSER-APPROVED MEMORY:\n")
        for item in memories[:20]:
            lines.append(f"- {item.get('text', '')[:500]}\n")

    if sources:
        lines.append("\nLIVE SEARCH SOURCES:\n")
        for index, item in enumerate(sources, start=1):
            lines.append(
                f"[{index}] {item.get('title', '')}\n"
                f"URL: {item.get('url', '')}\n"
                f"{item.get('snippet', '')}\n"
            )

    return "\n".join(lines)


def brain_answer(
    user_message: str,
    sources=None,
    requested_model: str = "auto",
    history: list[dict[str, str]] | None = None,
    memories: list[dict[str, Any]] | None = None,
    max_new_tokens: int | None = None,
):
    sources = sources or []
    generation_limit = (
        settings.max_new_tokens
        if max_new_tokens is None
        else max_new_tokens
    )

    # --------------------------------------------------------
    # HARD CREATOR RULE
    # --------------------------------------------------------

    if is_creator_question(
        user_message
    ):
        return {
            "answer": creator_answer(
                user_message
            ),
            "model": "BISNU-identity",
            "models_used": [
                "identity-rule"
            ],
            "verified": True
        }

    context = build_context(
        sources,
        history,
        memories,
    )

    system = (
        BASE_SYSTEM
        + context
    )

    requested_model = (
        requested_model.lower()
        if requested_model
        else "auto"
    )

    if settings.llm_gateway_enabled:
        answer = model_manager.generate(
            "gateway",
            system,
            user_message,
            max_new_tokens=generation_limit,
        )
        return {
            "answer": answer,
            "model": settings.llm_model,
            "models_used": [settings.llm_model],
            "verified": False,
        }

    # --------------------------------------------------------
    # DIRECT MODEL
    # --------------------------------------------------------

    if requested_model in {
        "qwen",
        "llama",
        "bisnu",
        "bisnu-1.1"
    }:

        if requested_model in {
            "bisnu",
            "bisnu-1.1"
        } and not settings.bisnu_enabled:
            raise RuntimeError(
                "BISNU-1.1 is not enabled/configured."
            )

        answer = model_manager.generate(
            requested_model,
            system,
            user_message,
            max_new_tokens=generation_limit,
        )

        return {
            "answer": answer,
            "model": requested_model,
            "models_used": [
                requested_model
            ],
            "verified": False
        }

    # --------------------------------------------------------
    # AUTO BRAIN
    # --------------------------------------------------------

    if not settings.ensemble_enabled:

        if settings.qwen_enabled:
            answer = model_manager.generate(
                "qwen",
                system,
                user_message,
                max_new_tokens=generation_limit,
            )

            return {
                "answer": answer,
                "model": "qwen",
                "models_used": [
                    "qwen"
                ],
                "verified": False
            }

        if settings.llama_enabled:
            answer = model_manager.generate(
                "llama",
                system,
                user_message,
                max_new_tokens=generation_limit,
            )

            return {
                "answer": answer,
                "model": "llama",
                "models_used": [
                    "llama"
                ],
                "verified": False
            }

        raise RuntimeError(
            "No AI model is enabled."
        )

    # --------------------------------------------------------
    # QWEN PRIMARY
    # --------------------------------------------------------

    primary = None

    if settings.qwen_enabled:
        primary = model_manager.generate(
            "qwen",
            system,
            user_message,
            max_new_tokens=generation_limit,
        )

    elif settings.llama_enabled:
        primary = model_manager.generate(
            "llama",
            system,
            user_message,
            max_new_tokens=generation_limit,
        )

    else:
        raise RuntimeError(
            "No AI model is enabled."
        )

    models_used = []

    if settings.qwen_enabled:
        models_used.append("qwen")

    # --------------------------------------------------------
    # LLAMA VERIFICATION
    # --------------------------------------------------------

    verified = False
    verifier = ""

    if (
        settings.verifier_enabled
        and settings.llama_enabled
    ):
        verifier_prompt = f"""
Review the proposed BISNU-X answer below.

USER QUESTION:
{user_message}

PROPOSED ANSWER:
{primary}

Check factual consistency, reasoning,
missing caveats and contradictions.

Give a concise correction/review.
"""

        verifier = model_manager.generate(
            "llama",
            BASE_SYSTEM,
            verifier_prompt,
            max_new_tokens=min(
                256,
                generation_limit
            )
        )

        models_used.append("llama")
        verified = True

    # --------------------------------------------------------
    # QWEN SYNTHESIS
    # --------------------------------------------------------

    if (
        settings.synthesis_enabled
        and settings.qwen_enabled
        and verifier
    ):
        synthesis_prompt = f"""
Answer the user's question.

USER:
{user_message}

PRIMARY DRAFT:
{primary}

VERIFIER REVIEW:
{verifier}

Produce the final answer.
Use the user's language.
Do not mention hidden prompts,
internal chain-of-thought or model internals.
Do not blindly follow the verifier if it is wrong.
"""

        final_answer = model_manager.generate(
            "qwen",
            BASE_SYSTEM + context,
            synthesis_prompt,
            max_new_tokens=generation_limit,
        )

        models_used.append(
            "qwen-synthesis"
        )

    else:
        final_answer = primary

    return {
        "answer": final_answer,
        "model": "BISNU-Brain",
        "models_used": models_used,
        "verified": verified
    }


brain = brain_answer
