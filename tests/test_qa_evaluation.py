import json
from pathlib import Path
from uuid import uuid4

from app.llm import LLMAnswer
from app.grounded_qa import has_question_relevant_passage
from app.qa_evaluation import evaluate_case
from scripts import evaluate_grounded_qa

CASES = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "grounded_qa_cases.json"
    ).read_text(encoding="utf-8")
)


def test_evaluation_fixture_covers_supported_and_unsupported_questions():
    assert len(CASES) >= 7
    assert any(case["id"] == "termination-vs-term" for case in CASES)
    assert any(case["expected_answerable"] for case in CASES)
    assert any(not case["expected_answerable"] for case in CASES)
    assert all(
        case["expected_concepts"] or not case["expected_answerable"]
        for case in CASES
    )


def test_evaluation_separates_valid_citation_from_relevant_citation():
    case = next(item for item in CASES if item["id"] == "governing-law")
    relevant_id = uuid4()
    irrelevant_id = uuid4()
    answer = LLMAnswer(
        answer="Delaware law governs.",
        answerable=True,
        citation_ids=[str(irrelevant_id)],
    )
    retrieved = [
        {
            "chunk_id": relevant_id,
            "text": "This Agreement shall be governed by the laws of Delaware.",
        },
        {
            "chunk_id": irrelevant_id,
            "text": "Each party must protect confidential information.",
        },
    ]

    result = evaluate_case(case, answer, retrieved)

    assert result["citation_ids_valid"] is True
    assert result["citation_relevant"] is False
    assert result["retrieval_contains_answer_passage"] is True
    assert result["supported_answer_correct"] is True


def test_evaluation_detects_retrieval_miss_separately_from_answer_quality():
    case = next(item for item in CASES if item["id"] == "governing-law")
    irrelevant_id = uuid4()
    answer = LLMAnswer(
        answer="The passages do not establish the governing law.",
        answerable=False,
        citation_ids=[],
    )

    result = evaluate_case(
        case,
        answer,
        [{"chunk_id": irrelevant_id, "text": "Confidentiality survives termination."}],
    )

    assert result["retrieval_contains_answer_passage"] is False
    assert result["answerability_correct"] is False


def test_evaluation_scores_correct_abstention_for_unsupported_question():
    case = next(item for item in CASES if item["id"] == "termination-vs-term")
    answer = LLMAnswer(
        answer="The provided contract passages do not establish the requested information.",
        answerable=False,
        citation_ids=[],
    )

    result = evaluate_case(case, answer, [{"chunk_id": uuid4(), "text": "Three-year term."}])

    assert result["answerability_correct"] is True
    assert result["unsupported_abstained"] is True


def test_question_relevance_gate_rejects_unrelated_but_valid_source():
    assert not has_question_relevant_passage(
        "What is the limitation of liability?",
        ["This Agreement is governed by Delaware law."],
    )
    assert not has_question_relevant_passage(
        "What is the payment amount?",
        ["Each party agrees to protect Confidential Information."],
    )


def test_question_relevance_gate_accepts_relevant_passages():
    assert has_question_relevant_passage(
        "What confidentiality obligations does this agreement impose?",
        ["Each party agrees to protect Confidential Information using reasonable care."],
    )
    assert has_question_relevant_passage(
        "What law governs this agreement?",
        ["This Agreement shall be governed by the laws of Delaware."],
    )


def test_live_evaluation_retrieval_is_limited_to_sample_nda(monkeypatch):
    document_id = uuid4()
    chunk_id = uuid4()
    source_text = "The agreement is governed by Delaware law."
    retrieved_chunk = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "file_name": evaluate_grounded_qa.EVALUATION_DOCUMENT,
        "text": source_text,
        "start_offset": 0,
        "end_offset": len(source_text),
        "similarity": 1.0,
    }

    class FakeEmbeddingProvider:
        dimension = 2

        def embed(self, _query):
            return [0.25, 0.75]

    class FakeCursor:
        def __init__(self):
            self.queries = []
            self.parameters = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, query, parameters):
            self.queries.append(query)
            self.parameters.append(parameters)

        def fetchall(self):
            if len(self.queries) == 1:
                return [{"id": document_id, "raw_text": source_text}]
            return [retrieved_chunk]

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()

        def cursor(self):
            return self.fake_cursor

    fake_connection = FakeConnection()
    monkeypatch.setattr(evaluate_grounded_qa, "embedding_provider", FakeEmbeddingProvider())
    monkeypatch.setattr(evaluate_grounded_qa, "ensure_embedding_profile", lambda *_args: None)

    chunks, sources = evaluate_grounded_qa._retrieve_sample_nda_chunks(
        fake_connection,
        str(uuid4()),
        "What law governs this agreement?",
    )

    document_query, retrieval_query = fake_connection.fake_cursor.queries
    assert "file_name = %s" in document_query
    assert fake_connection.fake_cursor.parameters[0][1] == "sample_nda.txt"
    assert "d.id = %s" in retrieval_query
    assert chunks == [retrieved_chunk]
    assert sources == {str(document_id): source_text}
