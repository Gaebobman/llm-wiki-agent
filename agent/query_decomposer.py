from __future__ import annotations

import re
from dataclasses import dataclass, field


STOPWORDS = {
    "그리고",
    "그",
    "그것",
    "그냥",
    "내",
    "너",
    "우리",
    "이",
    "이거",
    "이것",
    "저",
    "좀",
    "좀더",
    "좀더",
    "해줘",
    "해주세요",
    "해라",
    "주세요",
    "알려줘",
    "알려줘봐",
    "설명",
    "설명해줘",
    "대해",
    "관련",
    "방법",
    "어떻게",
    "무엇",
    "뭐",
    "왜",
    "언제",
    "어디",
    "혹시",
    "있어",
    "있나요",
    "있어?",
    "보여줘",
    "추가해줘",
    "수정해줘",
    "바꿔줘",
    "고쳐줘",
    "만들어줘",
}

UPDATE_HINTS = {
    "추가",
    "추가해",
    "추가해줘",
    "수정",
    "수정해",
    "수정해줘",
    "변경",
    "변경해",
    "변경해줘",
    "교체",
    "교체해",
    "삭제",
    "삭제해",
    "삭제해줘",
    "만들",
    "생성",
    "작성",
    "넣어",
    "반영",
    "고쳐",
    "개정",
}

RISKY_HINTS = {
    "삭제",
    "제거",
    "이동",
    "대규모",
    "rewrite",
    "replace",
    "drop",
    "cleanup",
    "reclassify",
    "rename",
}


@dataclass(frozen=True)
class QuerySection:
    terms: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    preferred_search: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryDecomposition:
    user_query: str
    intent: str
    requires_update: bool
    requires_approval: bool
    local_query: QuerySection
    global_query: QuerySection
    update_summary: str


def decompose_query(user_query: str) -> QueryDecomposition:
    tokens = _tokenize(user_query)
    quoted = _quoted_phrases(user_query)
    update_intent = _looks_like_update(user_query)
    risky = update_intent and _looks_risky(user_query)

    local_terms = _build_local_terms(tokens, quoted)
    global_terms = _build_global_terms(tokens, local_terms)

    relations = _relation_terms(user_query)
    intent = "update_existing_page" if update_intent else "answer_question"
    return QueryDecomposition(
        user_query=user_query,
        intent=intent,
        requires_update=update_intent,
        requires_approval=risky,
        local_query=QuerySection(
            terms=local_terms[:12],
            entities=local_terms[:8],
            themes=[],
            relations=[],
            preferred_search=["bm25", "keyword", "short_vector"],
        ),
        global_query=QuerySection(
            terms=[],
            entities=[],
            themes=global_terms[:12],
            relations=relations[:8],
            preferred_search=["semantic_vector", "hyde", "rerank"],
        ),
        update_summary=_summarize_update(user_query, update_intent),
    )


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[0-9A-Za-z가-힣_./+-]+", text.lower())
    return [token for token in raw if token not in STOPWORDS]


def _quoted_phrases(text: str) -> list[str]:
    phrases = re.findall(r"[\"“](.+?)[\"”]", text)
    return [phrase.strip().lower() for phrase in phrases if phrase.strip()]


def _looks_like_update(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in UPDATE_HINTS)


def _looks_risky(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in RISKY_HINTS)


def _build_local_terms(tokens: list[str], quoted: list[str]) -> list[str]:
    items: list[str] = []
    for item in quoted + tokens:
        if item and item not in items and _looks_local(item):
            items.append(item)
    if not items:
        items.extend(_top_keywords(tokens, limit=6))
    return items


def _build_global_terms(tokens: list[str], local_terms: list[str]) -> list[str]:
    items: list[str] = []
    local_set = set(local_terms)
    for token in tokens:
        if token in local_set:
            continue
        if token in STOPWORDS:
            continue
        if token not in items:
            items.append(token)
    if not items:
        items.extend(_top_keywords(tokens, limit=8))
    return items


def _looks_local(term: str) -> bool:
    return bool(
        re.search(r"[0-9]", term)
        or re.search(r"[A-Z]", term)
        or "/" in term
        or "." in term
        or term.endswith(("doc", "docx", "pptx", "xlsx", "pdf"))
        or len(term) <= 24
    )


def _top_keywords(tokens: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for token in tokens:
        if token in STOPWORDS:
            continue
        if token not in result:
            result.append(token)
        if len(result) >= limit:
            break
    return result


def _relation_terms(text: str) -> list[str]:
    relations: list[str] = []
    for token in ["관계", "흐름", "절차", "정책", "원인", "결과", "비교", "구조", "거버넌스", "workflow"]:
        if token in text.lower() or token in text:
            relations.append(token)
    return relations


def _summarize_update(text: str, is_update: bool) -> str:
    if not is_update:
        return text.strip()
    return text.strip().replace("\n", " ")
