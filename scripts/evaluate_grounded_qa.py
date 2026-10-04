import argparse
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

from app.config import OLLAMA_BASE_URL
from app.db import get_connection
from app.embedding_profile import ensure_embedding_profile
from app.embeddings import embedding_provider
from app.grounded_qa import ABSTENTION_ANSWER, enforce_answerability
from app.llm import LLMAnswer, OllamaLLMProvider, RetrievedChunk
from app.qa_evaluation import evaluate_case
from app.ingestion import vector_literal

EVALUATION_CASES = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "grounded_qa_cases.json"
)
EVALUATION_DOCUMENT = "sample_nda.txt"


def _retrieve_sample_nda_chunks(
    connection: Any,
    contract_id: str,
    query: str,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    ensure_embedding_profile(connection, embedding_provider)
    query_embedding = embedding_provider.embed(query)
    if len(query_embedding) != embedding_provider.dimension:
        raise ValueError(
            f"Expected {embedding_provider.dimension}-dimensional embeddings, "
            f"got {len(query_embedding)}."
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, raw_text
            FROM documents
            WHERE contract_id = %s AND file_name = %s
            """,
            (contract_id, EVALUATION_DOCUMENT),
        )
        documents = cursor.fetchall()
        if len(documents) != 1:
            raise ValueError(
                f"Expected exactly one {EVALUATION_DOCUMENT!r} document in "
                f"contract {contract_id}, found {len(documents)}."
            )
        document = documents[0]

        cursor.execute(
            """
            SELECT dc.id AS chunk_id, dc.document_id, d.file_name, d.mime_type,
                   c.title AS contract_title, c.contract_type,
                   dc.chunk_index, dc.text, dc.start_offset, dc.end_offset,
                   1 - (dc.embedding <=> %s::vector) AS similarity
            FROM document_chunks AS dc
            JOIN documents AS d ON d.id = dc.document_id
            JOIN contracts AS c ON c.id = d.contract_id
            WHERE d.contract_id = %s AND d.id = %s
            ORDER BY dc.embedding <=> %s::vector
            LIMIT %s
            """,
            (
                vector_literal(query_embedding),
                contract_id,
                document["id"],
                vector_literal(query_embedding),
                limit,
            ),
        )
        chunks = cursor.fetchall()

    return chunks, {str(document["id"]): document["raw_text"] or ""}


def _case_result(
    case: dict[str, Any],
    provider: OllamaLLMProvider,
    contract_id: str,
) -> dict[str, Any]:
    retrieval_started = time.perf_counter()
    with get_connection() as connection:
        chunks, sources = _retrieve_sample_nda_chunks(
            connection, contract_id, case["question"], limit=5
        )
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
    context = [
        RetrievedChunk(chunk_id=row["chunk_id"], text=row["text"])
        for row in chunks
    ]

    generation_started = time.perf_counter()
    model_answer = provider.generate(case["question"], context)
    generation_ms = (time.perf_counter() - generation_started) * 1000
    model_assessment = evaluate_case(case, model_answer, chunks)
    answer = enforce_answerability(case["question"], context, model_answer)
    if not answer.answerable or not answer.citation_ids:
        answer = LLMAnswer(
            answer=ABSTENTION_ANSWER,
            answerable=False,
            citation_ids=answer.citation_ids,
        )
    assessment = evaluate_case(case, answer, chunks)

    chunks_by_id = {str(row["chunk_id"]): row for row in chunks}
    citation_checks = []
    for citation_id in answer.citation_ids:
        normalized_id = str(citation_id)
        row = chunks_by_id.get(normalized_id)
        exact_source_match = False
        if row is not None:
            source = sources[str(row["document_id"])]
            expected_text = source[
                row["start_offset"] : row["end_offset"]
            ]
            exact_source_match = expected_text == row["text"]
        citation_checks.append(
            {
                "chunk_id": str(citation_id),
                "in_retrieved_results": row is not None,
                "matches_document_source_offsets": exact_source_match,
            }
        )

    return {
        "id": case["id"],
        "question": case["question"],
        "latency_ms": {
            "retrieval": round(retrieval_ms, 1),
            "generation": round(generation_ms, 1),
        },
        "retrieval": [
            {
                "rank": rank,
                "chunk_id": str(row["chunk_id"]),
                "document": row["file_name"],
                "similarity": round(row["similarity"], 4),
                "start_offset": row["start_offset"],
                "end_offset": row["end_offset"],
                "contains_answer_evidence": any(
                    phrase.casefold() in row["text"].casefold()
                    for phrase in case["source_evidence_phrases"]
                ),
                "text": row["text"],
            }
            for rank, row in enumerate(chunks, start=1)
        ],
        "assessment": assessment,
        "model_assessment": model_assessment,
        "model_output": {
            "answer": model_answer.answer,
            "answerable": model_answer.answerable,
            "citation_ids": [
                str(citation_id) for citation_id in model_answer.citation_ids
            ],
            "schema_valid": True,
        },
        "citation_checks": citation_checks,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in results if "error" not in row]
    supported = [
        row for row in successful if row["assessment"]["expected_answerable"]
    ]
    unsupported = [
        row for row in successful if not row["assessment"]["expected_answerable"]
    ]
    latencies = [
        row["latency_ms"]["generation"]
        for row in successful
    ]

    def rate(values: list[bool | None]) -> float | None:
        scored = [value for value in values if value is not None]
        return (
            round(sum(scored) / len(scored), 3)
            if scored
            else None
        )

    all_citations = [
        citation
        for row in successful
        for citation in row["citation_checks"]
    ]
    supported_model_rows = [
        row for row in successful if row["model_assessment"]["expected_answerable"]
    ]
    unsupported_model_rows = [
        row for row in successful if not row["model_assessment"]["expected_answerable"]
    ]
    non_placeholder_answers = [
        not re.fullmatch(
            r"(?:answerable\s*=\s*(?:true|false)|true|false|null|none)",
            row["model_output"]["answer"].strip(),
            flags=re.IGNORECASE,
        )
        for row in supported_model_rows
    ]
    return {
        "cases": len(results),
        "structured_output_success": round(len(successful) / len(results), 3),
        "non_placeholder_supported_answer_rate": rate(non_placeholder_answers),
        "model_answerability_accuracy": rate(
            [row["model_assessment"]["answerability_correct"] for row in successful]
        ),
        "model_supported_concept_accuracy": rate(
            [
                row["model_assessment"]["supported_answer_correct"]
                for row in supported_model_rows
            ]
        ),
        "model_unsupported_abstention_rate": rate(
            [
                row["model_assessment"]["unsupported_abstained"]
                for row in unsupported_model_rows
            ]
        ),
        "answerability_accuracy": rate(
            [row["assessment"]["answerability_correct"] for row in successful]
        ),
        "supported_concept_accuracy": rate(
            [row["assessment"]["supported_answer_correct"] for row in supported]
        ),
        "unsupported_abstention_rate": rate(
            [row["assessment"]["unsupported_abstained"] for row in unsupported]
        ),
        "retrieval_evidence_recall": rate(
            [
                row["assessment"]["retrieval_contains_answer_passage"]
                for row in supported
            ]
        ),
        "supported_citation_relevance": rate(
            [row["assessment"]["citation_relevant"] for row in supported]
        ),
        "citation_ids_valid": rate(
            [row["assessment"]["citation_ids_valid"] for row in successful]
        ),
        "citation_source_offset_accuracy": rate(
            [
                citation["matches_document_source_offsets"]
                for citation in all_citations
            ]
        ),
        "generation_latency_ms": {
            "median": round(statistics.median(latencies), 1)
            if latencies
            else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate grounded Q&A against a fixture and live Ollama models."
    )
    parser.add_argument("--contract-id", required=True)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["llama3.2:3b", "phi:latest", "mistral:latest"],
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path instead of stdout.",
    )
    args = parser.parse_args()
    cases = json.loads(EVALUATION_CASES.read_text(encoding="utf-8"))
    report = {
        "embedding_provider": embedding_provider.provider_name,
        "embedding_model": embedding_provider.model_name,
        "embedding_dimension": embedding_provider.dimension,
        "ollama_base_url": OLLAMA_BASE_URL,
        "evaluation_document": EVALUATION_DOCUMENT,
        "models": {},
    }
    failed_cases = []

    for model in args.models:
        provider = OllamaLLMProvider(
            OLLAMA_BASE_URL,
            model,
            timeout_seconds=300,
        )
        results = []
        for case in cases:
            try:
                results.append(_case_result(case, provider, args.contract_id))
            except Exception as exc:
                failed_cases.append((model, case["id"]))
                results.append(
                    {
                        "id": case["id"],
                        "question": case["question"],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        report["models"][model] = {
            "summary": _summary(results),
            "results": results,
        }

    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is None:
        print(report_json)
    else:
        args.output.write_text(report_json, encoding="utf-8")
    if failed_cases:
        failed_labels = ", ".join(
            f"{model}/{case_id}" for model, case_id in failed_cases
        )
        raise SystemExit(
            f"Evaluation incomplete: {len(failed_cases)} case(s) failed "
            f"({failed_labels})."
        )


if __name__ == "__main__":
    main()
