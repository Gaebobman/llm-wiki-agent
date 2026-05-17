from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent.query_decomposer import decompose_query


def test_decompose_update_context_prioritizes_mutation_intent():
    result = decompose_query("RAG 토픽 문서에 qmd 검색 라우팅 내용", command_context="update")

    assert result.intent == "update_existing_page"
    assert result.requires_update is True
    assert result.planner_source == "fallback"
    assert result.local_query.terms
    assert "qmd" in result.local_query.terms


def test_decompose_question_defaults_to_answer_intent():
    result = decompose_query("연구과제 계약 절차가 어떻게 되나요?")

    assert result.intent == "answer_question"
    assert result.requires_update is False
    assert result.crud_action == "read"


def test_decompose_uses_llm_planner_schema_without_keyword_rules(tmp_path):
    planner = tmp_path / "planner.py"
    planner.write_text(
        "\n".join(
            [
                "import json, sys",
                "json.loads(sys.stdin.read())",
                "print(json.dumps({",
                "  'crud_action': 'update',",
                "  'intent': 'update_existing_page',",
                "  'destructive_action': 'false',",
                "  'risk_level': 'low',",
                "  'requires_approval': True,",
                "  'local_query': {'terms': ['DRT1017'], 'entities': ['DRT1017']},",
                "  'global_query': {'themes': ['BMS'], 'relations': ['supports']},",
                "  'update_summary': 'Keep existing material and add BMS context.',",
                "  'confidence': 0.91,",
                "  'rationale': 'The request explicitly says not to delete.'",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    result = decompose_query(
        "DRT1017에서 삭제하지 말고 BMS 문맥만 보강",
        command_context="update",
        planner_command=f"{sys.executable} {planner}",
    )

    assert result.planner_source == "llm"
    assert result.crud_action == "update"
    assert result.destructive_action is False
    assert result.risk_level == "low"
    assert result.local_query.entities == ["DRT1017"]


def test_decompose_uses_openai_compatible_chat_api():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.server.request_body = self.rfile.read(length).decode("utf-8")
            body = {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"crud_action":"delete","intent":"delete_wiki_content",'
                                '"destructive_action":true,"risk_level":"high",'
                                '"requires_approval":true,'
                                '"local_query":{"terms":["obsolete"],"entities":[]},'
                                '"global_query":{"themes":["cleanup"],"relations":[]},'
                                '"update_summary":"Remove obsolete content.",'
                                '"confidence":0.88,"rationale":"The request asks for removal."}'
                            )
                        }
                    }
                ]
            }
            payload = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        result = decompose_query(
            "remove obsolete content",
            command_context="update",
            llm_base_url=f"http://127.0.0.1:{server.server_port}/v1",
            llm_model="test-model",
            llm_api_key="test-key",
        )
    finally:
        thread.join(timeout=5)
        server.server_close()

    assert result.planner_source == "llm_api"
    assert result.crud_action == "delete"
    assert result.destructive_action is True
    assert result.risk_level == "high"
