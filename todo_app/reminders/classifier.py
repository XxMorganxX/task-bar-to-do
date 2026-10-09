"""Classify a todo into a reminder type + importance + effort.

Component independence: the engine depends only on the ``Classifier`` ABC.
Each provider holds all of its own SDK-specific logic. The fallback chain is
OpenAI (primary) -> Gemini -> heuristic keyword matcher: every LLM classifier
delegates to the next link when its own call fails, so classification always
returns a result. ``make_classifier`` is the single wiring point.
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from . import config
from .types import ClassifierResult, ReminderType

logger = logging.getLogger(__name__)


class Classifier(ABC):
    @abstractmethod
    def classify(self, todo: Dict[str, Any]) -> ClassifierResult:
        ...


# ---------------------------------------------------------------------------
# Heuristic fallback (no external dependency)
# ---------------------------------------------------------------------------
_SCHEDULED_KEYWORDS = (
    "appointment", "meeting", "call", "event", "flight", "reservation",
    "interview", "class", "lecture", "dinner", "lunch", "pickup", "pick up",
)
_DEADLINE_KEYWORDS = (
    "submit", "deadline", "due", "pay", "file", "assignment", "renew",
    "register", "apply", "send", "turn in", "return",
)
_ADMIN_KEYWORDS = (
    "email", "text", "reply", "rsvp", "confirm", "book", "order", "schedule",
    "sign", "form", "venmo",
)
_PROJECT_KEYWORDS = (
    "write", "build", "plan", "study", "prepare", "finish", "project", "essay",
    "report", "research", "design", "draft", "review", "read",
)
_HABIT_KEYWORDS = (
    "daily", "every day", "everyday", "weekly", "gym", "water", "vitamins",
    "journal", "stretch", "meditate", "walk",
)
_HIGH_IMPORTANCE_KEYWORDS = (
    "urgent", "important", "exam", "final", "taxes", "rent", "deadline",
    "critical", "asap", "interview", "medical", "doctor",
)


class HeuristicClassifier(Classifier):
    name = "heuristic"

    def classify(self, todo: Dict[str, Any]) -> ClassifierResult:
        text = f"{todo.get('title') or ''} {todo.get('details') or ''}".lower()
        has_due = bool(todo.get("due_at"))

        is_admin = any(k in text for k in _ADMIN_KEYWORDS)
        is_project = any(k in text for k in _PROJECT_KEYWORDS)
        is_habit = any(k in text for k in _HABIT_KEYWORDS)

        if is_project:
            effort = 120
        elif is_admin:
            effort = 10
        else:
            effort = 30

        importance = 0.5
        if any(k in text for k in _HIGH_IMPORTANCE_KEYWORDS):
            importance = 0.85
        elif is_admin and not is_project:
            importance = 0.35

        if is_habit and not has_due:
            reminder_type = ReminderType.HABIT_ROUTINE
        elif has_due:
            if any(k in text for k in _SCHEDULED_KEYWORDS) and not any(
                k in text for k in _DEADLINE_KEYWORDS
            ):
                reminder_type = ReminderType.SCHEDULED_POINT
            else:
                reminder_type = ReminderType.HARD_DEADLINE
        else:
            if effort <= config.LOW_EFFORT_MAX_MINUTES and importance < 0.6:
                reminder_type = ReminderType.LOW_EFFORT_ADMIN
            else:
                reminder_type = ReminderType.FLOATING_IMPORTANT

        return ClassifierResult(
            reminder_type=reminder_type,
            importance=importance,
            effort_minutes=effort,
            classifier=self.name,
            confidence=0.5,
        )


# ---------------------------------------------------------------------------
# Gemini classifier (fallback)
# ---------------------------------------------------------------------------
class GeminiClassifier(Classifier):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        import google.generativeai as genai

        self._genai = genai
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiClassifier")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            config.CLASSIFIER_FALLBACK_MODEL,
            generation_config={
                "temperature": config.CLASSIFIER_TEMPERATURE,
                "response_mime_type": "application/json",
            },
            system_instruction=config.CLASSIFIER_SYSTEM_PROMPT,
        )
        self._fallback = HeuristicClassifier()

    def classify(self, todo: Dict[str, Any]) -> ClassifierResult:
        prompt = config.CLASSIFIER_USER_PROMPT_TEMPLATE.format(
            title=todo.get("title") or "",
            details=todo.get("details") or "(none)",
            has_due=bool(todo.get("due_at")),
            due_at=todo.get("due_at") or "(none)",
        )
        try:
            response = self._model.generate_content(prompt)
            data = _parse_json(_response_text(response))
            return _result_from_data(data, classifier=self.name)
        except Exception as exc:  # pragma: no cover - network/parse variance
            logger.warning("Gemini classification failed, using heuristic: %s", exc)
            return self._fallback.classify(todo)


# ---------------------------------------------------------------------------
# OpenAI classifier (primary)
# ---------------------------------------------------------------------------
class OpenAIClassifier(Classifier):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        from openai import OpenAI

        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIClassifier")
        self._client = OpenAI(api_key=api_key)
        self._model_name = config.CLASSIFIER_MODEL
        self._fallback = _build_fallback_classifier()

    def classify(self, todo: Dict[str, Any]) -> ClassifierResult:
        user_prompt = config.CLASSIFIER_USER_PROMPT_TEMPLATE.format(
            title=todo.get("title") or "",
            details=todo.get("details") or "(none)",
            has_due=bool(todo.get("due_at")),
            due_at=todo.get("due_at") or "(none)",
        )
        messages = [
            {"role": "system", "content": config.CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            content = self._complete(messages)
            data = _parse_json(content)
            return _result_from_data(data, classifier=self.name)
        except Exception as exc:  # pragma: no cover - network/parse variance
            logger.warning("OpenAI classification failed, falling back: %s", exc)
            return self._fallback.classify(todo)

    def _complete(self, messages: Any) -> str:
        kwargs: Dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": config.CLASSIFIER_TEMPERATURE,
        }
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Some models (e.g. gpt-5 reasoning minis) reject a custom temperature;
            # retry once with the API default before deferring to the fallback chain.
            if "temperature" in str(exc).lower():
                kwargs.pop("temperature", None)
                response = self._client.chat.completions.create(**kwargs)
            else:
                raise
        return response.choices[0].message.content or ""


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return text
    parts = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            piece = getattr(part, "text", None)
            if piece:
                parts.append(piece)
    return "".join(parts)


def _parse_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("empty classifier response")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _result_from_data(data: Dict[str, Any], *, classifier: str) -> ClassifierResult:
    raw_type = str(data.get("reminder_type", "")).strip().lower()
    try:
        reminder_type = ReminderType(raw_type)
    except ValueError:
        reminder_type = ReminderType.FLOATING_IMPORTANT

    try:
        importance = float(data.get("importance", 0.5))
    except (TypeError, ValueError):
        importance = 0.5
    importance = max(0.0, min(1.0, importance))

    try:
        effort = int(float(data.get("effort_minutes", 30)))
    except (TypeError, ValueError):
        effort = 30
    effort = max(1, effort)

    return ClassifierResult(
        reminder_type=reminder_type,
        importance=importance,
        effort_minutes=effort,
        classifier=classifier,
    )


def _build_fallback_classifier() -> Classifier:
    """Best classifier below OpenAI: Gemini when configured, else the heuristic."""

    if os.getenv("GEMINI_API_KEY"):
        try:
            return GeminiClassifier()
        except Exception as exc:  # pragma: no cover - import/config variance
            logger.warning("GeminiClassifier unavailable, using heuristic: %s", exc)
    return HeuristicClassifier()


def make_classifier(prefer_llm: bool = True) -> Classifier:
    """Wire the classifier following the OpenAI -> Gemini -> heuristic chain."""

    if prefer_llm and os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIClassifier()
        except Exception as exc:  # pragma: no cover - import/config variance
            logger.warning("OpenAIClassifier unavailable, trying Gemini: %s", exc)
    if prefer_llm and os.getenv("GEMINI_API_KEY"):
        try:
            return GeminiClassifier()
        except Exception as exc:  # pragma: no cover - import/config variance
            logger.warning("GeminiClassifier unavailable, using heuristic: %s", exc)
    return HeuristicClassifier()


__all__ = [
    "Classifier",
    "HeuristicClassifier",
    "GeminiClassifier",
    "OpenAIClassifier",
    "make_classifier",
]
