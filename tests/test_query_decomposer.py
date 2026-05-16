from __future__ import annotations

from agent.query_decomposer import decompose_query


def test_decompose_update_request_prioritizes_update_intent():
    result = decompose_query("RAG 토픽 문서에 qmd 검색 라우팅 내용 추가해줘")

    assert result.intent == "update_existing_page"
    assert result.requires_update is True
    assert result.local_query.terms
    assert "qmd" in result.local_query.terms
    assert any(term in result.global_query.themes for term in ["검색", "라우팅"])


def test_decompose_question_defaults_to_answer_intent():
    result = decompose_query("연구과제 계약 절차가 어떻게 되나요?")

    assert result.intent == "answer_question"
    assert result.requires_update is False
    assert "계약" in result.global_query.themes or "절차" in result.global_query.relations
