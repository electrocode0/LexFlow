import re
from typing import Any

from app.llm import LLMAnswer


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def evaluate_case(
    case: dict[str, Any],
    answer: LLMAnswer,
    retrieved_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    retrieved_by_id = {str(chunk["chunk_id"]): chunk for chunk in retrieved_chunks}
    cited_chunks = []
    valid_citation_count = 0
    for citation_id in answer.citation_ids:
        normalized_id = str(citation_id)
        chunk = retrieved_by_id.get(normalized_id)
        if chunk is not None:
            valid_citation_count += 1
            cited_chunks.append(chunk)
    expected_concepts = case["expected_concepts"]
    normalized_answer = _normalized_text(answer.answer)
    concepts_covered = [
        concept
        for concept in expected_concepts
        if _normalized_text(concept) in normalized_answer
    ]
    evidence_phrases = case["source_evidence_phrases"]

    def includes_evidence(chunks: list[dict[str, Any]]) -> bool:
        normalized_passages = [
            _normalized_text(chunk["text"]) for chunk in chunks
        ]
        return any(
            _normalized_text(phrase) in passage
            for phrase in evidence_phrases
            for passage in normalized_passages
        )

    expected_answerable = case["expected_answerable"]
    citation_ids_valid = valid_citation_count == len(answer.citation_ids)
    answerable = answer.answerable and bool(cited_chunks)
    relevant_citation = includes_evidence(cited_chunks) if expected_answerable else None
    concepts_complete = len(concepts_covered) == len(expected_concepts)

    return {
        "answerability_correct": answerable == expected_answerable,
        "answerable": answerable,
        "expected_answerable": expected_answerable,
        "supported_concepts_covered": concepts_covered,
        "supported_answer_correct": (
            answerable and concepts_complete if expected_answerable else None
        ),
        "unsupported_abstained": (
            not answerable if not expected_answerable else None
        ),
        "retrieval_contains_answer_passage": (
            includes_evidence(retrieved_chunks) if expected_answerable else None
        ),
        "citation_ids_valid": citation_ids_valid,
        "citation_relevant": relevant_citation,
        "citation_ids": [str(citation_id) for citation_id in answer.citation_ids],
        "answer": answer.answer,
    }
