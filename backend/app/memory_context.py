"""Context selection and summarization: spend the budget on what matters.

AATM has no tokenizer for an arbitrary model, so this module does not pretend to
count provider tokens. It counts *words* and states that plainly, because a fake
token count would be worse than an honest approximation.

Selection is deterministic and explainable:

1. **Relevance** — keyword overlap with the request (the same scoring the memory
   search uses), so nothing is selected by luck.
2. **Scope priority** — a requirement or decision outranks incidental notes when
   the budget is tight, because losing an accepted decision is more expensive
   than losing a scratch pad.
3. **Recency** — the tiebreaker when relevance and priority are equal.
4. **Budget** — selection stops at the word budget; excluded entries are listed
   with the reason, so the omission is visible rather than silent.

Summarization is **extractive**, never abstractive: each summary is a real
sentence from the entry. AATM cannot paraphrase without a model, and inventing a
summary would be dishonest.
"""

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.memory import list_memory
from app.models import MemoryEntry

# Which scopes matter most when the budget forces a choice. Requirements and
# decisions are the most expensive things to lose; scratch notes are the cheapest.
SCOPE_PRIORITY = {
    "decision": 100,
    "project": 70,
    "global": 60,
    "agent": 40,
    "task": 30,
}
KIND_HINTS = {
    "requirement": ("requirement", "acceptance", "must", "shall"),
    "architecture": ("architecture", "design", "layer", "component"),
    "issue": ("issue", "bug", "known issue", "workaround", "problem"),
    "lesson": ("lesson", "retrospective", "learned", "avoid"),
    "convention": ("convention", "style", "naming", "standard"),
}
_WORD = re.compile(r"[A-Za-z0-9_\u0600-\u06FF][A-Za-z0-9_\-\u0600-\u06FF]*")
_SENTENCE = re.compile(r"(?<=[.!?\u061F\u06D4])\s+|\n+")

DEFAULT_WORD_BUDGET = 400
MAX_WORD_BUDGET = 4000


class ContextError(ValueError):
    """A safe, user-facing context-selection failure."""


def count_words(text: str) -> int:
    """A word count, named as such: it is not a provider token count."""
    return len(_WORD.findall(text or ""))


def classify(entry: MemoryEntry) -> str:
    """Label an entry by the kind of knowledge it holds, from its own words."""
    haystack = f"{entry.title} {entry.content} {' '.join(entry.tags or [])}".lower()
    for kind, hints in KIND_HINTS.items():
        if any(hint in haystack for hint in hints):
            return kind
    return "note"


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text or "") if part.strip()]


def summarize_entry(entry: MemoryEntry, *, max_words: int = 40, query_terms: list[str] | None = None) -> dict[str, object]:
    """Extractive summary: pick real sentences, never generate new ones."""
    sentences = _sentences(entry.content) or _sentences(entry.title)
    if not sentences:
        return {
            "memory_id": entry.id,
            "summary": entry.title,
            "method": "title_only",
            "sentences_used": 0,
            "words": count_words(entry.title),
            "note": "The entry has no body, so its title is the only honest summary.",
        }

    terms = [term.lower() for term in (query_terms or [])]

    def score(sentence: str) -> tuple[int, int]:
        lowered = sentence.lower()
        hits = sum(1 for term in terms if term in lowered)
        # Earlier sentences usually carry the point; use position as a tiebreaker.
        return (-hits, sentences.index(sentence))

    chosen: list[str] = []
    used = 0
    for sentence in sorted(sentences, key=score):
        size = count_words(sentence)
        if used + size > max_words and chosen:
            continue
        if size > max_words and not chosen:
            # A single long sentence: take a real prefix rather than nothing,
            # and mark it so a reader knows it was cut.
            words = _WORD.findall(sentence)[:max_words]
            chosen.append(" ".join(words) + "…")
            used = max_words
            break
        chosen.append(sentence)
        used += size
        if used >= max_words:
            break

    order = {sentence: index for index, sentence in enumerate(sentences)}
    ordered = sorted(chosen, key=lambda item: order.get(item.rstrip("…"), order.get(item, 0)))
    return {
        "memory_id": entry.id,
        "summary": " ".join(ordered),
        "method": "extractive",
        "sentences_used": len(ordered),
        "words": used,
        "note": "Sentences are copied verbatim from the entry; AATM has no model to paraphrase with.",
    }


def select_context(
    db: Session,
    *,
    project_id: str | None,
    query: str = "",
    word_budget: int = DEFAULT_WORD_BUDGET,
    include_scopes: list[str] | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, object]:
    """Choose the memory that fits the budget, and explain every choice."""
    if word_budget < 10 or word_budget > MAX_WORD_BUDGET:
        raise ContextError(f"word_budget must be between 10 and {MAX_WORD_BUDGET}.")
    scopes = [scope for scope in (include_scopes or []) if scope]
    known = set(SCOPE_PRIORITY)
    unknown = [scope for scope in scopes if scope not in known]
    if unknown:
        raise ContextError(f"Unknown scope(s): {', '.join(unknown)}. Allowed: {', '.join(sorted(known))}.")

    candidates = list_memory(db, project_id=project_id)
    if scopes:
        candidates = [entry for entry in candidates if entry.scope in scopes]
    if agent_id:
        candidates = [entry for entry in candidates if entry.agent_id == agent_id or entry.scope != "agent"]
    if task_id:
        candidates = [entry for entry in candidates if entry.task_id == task_id or entry.scope != "task"]

    terms = [term.lower() for term in _WORD.findall(query)] if query else []
    now = datetime.now(timezone.utc)

    def relevance(entry: MemoryEntry) -> float:
        if not terms:
            return 0.0
        haystack = f"{entry.title} {entry.content} {' '.join(entry.tags or [])}".lower()
        hits = sum(1 for term in terms if term in haystack)
        title_hits = sum(1 for term in terms if term in entry.title.lower())
        return round(hits / len(terms) + 0.25 * title_hits, 4)

    def age_days(entry: MemoryEntry) -> float:
        stamp = entry.updated_at or entry.created_at
        if stamp is None:
            return 3650.0
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max((now - stamp).total_seconds() / 86400, 0.0)

    ranked = sorted(
        candidates,
        key=lambda entry: (
            -relevance(entry),
            -SCOPE_PRIORITY.get(entry.scope, 0),
            age_days(entry),
            entry.title,
        ),
    )

    selected: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    used_words = 0
    for entry in ranked:
        size = count_words(entry.title) + count_words(entry.content)
        if size == 0:
            excluded.append({"memory_id": entry.id, "title": entry.title, "reason": "empty"})
            continue
        if used_words + size > word_budget:
            # Try a summary before dropping it: a relevant entry cut to a real
            # sentence pair is better than losing it.
            remaining = word_budget - used_words
            if remaining >= 25:
                summary = summarize_entry(entry, max_words=min(remaining - 5, 60), query_terms=terms)
                if summary["words"] <= remaining:
                    selected.append(
                        {
                            "memory_id": entry.id,
                            "title": entry.title,
                            "scope": entry.scope,
                            "kind": classify(entry),
                            "relevance": relevance(entry),
                            "words": summary["words"],
                            "included_as": "summary",
                            "summary": summary["summary"],
                            "summary_method": summary["method"],
                        }
                    )
                    used_words += int(summary["words"])
                    continue
            excluded.append(
                {
                    "memory_id": entry.id,
                    "title": entry.title,
                    "reason": f"over_budget (needs {size}, {word_budget - used_words} left)",
                }
            )
            continue
        selected.append(
            {
                "memory_id": entry.id,
                "title": entry.title,
                "scope": entry.scope,
                "kind": classify(entry),
                "relevance": relevance(entry),
                "words": size,
                "included_as": "full",
                "summary": None,
                "summary_method": None,
            }
        )
        used_words += size

    kinds: dict[str, int] = {}
    for item in selected:
        kinds[str(item["kind"])] = kinds.get(str(item["kind"]), 0) + 1

    return {
        "project_id": project_id,
        "query": query,
        "budget": {
            "word_budget": word_budget,
            "words_used": used_words,
            "words_remaining": max(word_budget - used_words, 0),
            "unit": "words",
            "note": "Word counts, not provider tokens: AATM has no tokenizer for an arbitrary model.",
        },
        "selected": selected,
        "excluded": excluded,
        "stats": {
            "candidates": len(candidates),
            "selected": len(selected),
            "summarized": sum(1 for item in selected if item["included_as"] == "summary"),
            "excluded": len(excluded),
            "by_kind": kinds,
        },
        "ranking": {
            "order": ["relevance", "scope_priority", "recency", "title"],
            "scope_priority": SCOPE_PRIORITY,
            "note": "Deterministic: the same memory and query always produce the same selection.",
        },
        "note": "Nothing is invented. Excluded entries are listed with the reason they were omitted.",
    }
