import re

from app.llm import LLMAnswer, RetrievedChunk

ABSTENTION_ANSWER = "The provided contract passages do not establish the requested information."
_WORD_PATTERN = re.compile(r"[a-z]+")

_TERMINATION_QUESTION = re.compile(
    r"\b(?:terminat\w*|cancel\w*|resciss\w*|end\s+(?:this|the)\s+agreement)\b",
    re.IGNORECASE,
)
_QUESTION_STOP_WORDS = {
    "a",
    "about",
    "agreement",
    "are",
    "can",
    "does",
    "for",
    "how",
    "impose",
    "is",
    "may",
    "of",
    "the",
    "this",
    "what",
    "when",
    "which",
    "who",
    "with",
}
_TOPIC_ALIASES = {
    "amount": ("amount", "payment", "fee", "price"),
    "effective": ("effective", "term", "duration", "year"),
    "indemnif": ("indemnif",),
    "law": ("law", "govern"),
    "liability": ("liability", "liable"),
    "limit": ("limit", "cap"),
    "long": ("term", "duration", "effective", "year"),
    "obligation": ("obligation", "must", "shall", "agree", "protect"),
    "payment": ("payment", "fee", "invoice", "price"),
    "use": ("use", "purpose"),
}
_EXPLICIT_TERMINATION_PROCEDURE = re.compile(
    r"\b(?:"
    r"(?:may|can|shall|must|will|is\s+entitled\s+to)\s+terminate|"
    r"termination\s+(?:for|upon|on|by|requires)|"
    r"right\s+to\s+terminate|"
    r"terminate\s+(?:this|the)\s+agreement|"
    r"may\s+end\s+(?:this|the)\s+agreement|"
    r"cancel\s+(?:this|the)\s+agreement"
    r")\b",
    re.IGNORECASE,
)
_DURATION_LANGUAGE = re.compile(
    r"\b(?:term|effective|duration|expire\w*|for\s+\d+\s+(?:days|months|years))\b",
    re.IGNORECASE,
)


def enforce_answerability(
    question: str,
    context: list[RetrievedChunk],
    answer: LLMAnswer,
) -> LLMAnswer:
    context_text = "\n".join(chunk.text for chunk in context)
    if (
        _TERMINATION_QUESTION.search(question)
        and not _EXPLICIT_TERMINATION_PROCEDURE.search(context_text)
    ):
        return LLMAnswer(
            answer=ABSTENTION_ANSWER,
            answerable=False,
            citation_ids=answer.citation_ids,
        )
    context_by_id = {str(chunk.chunk_id): chunk.text for chunk in context}
    cited_text = [
        context_by_id[str(citation_id)]
        for citation_id in answer.citation_ids
        if str(citation_id) in context_by_id
    ]
    if answer.answerable and not has_question_relevant_passage(question, cited_text):
        return LLMAnswer(
            answer=ABSTENTION_ANSWER,
            answerable=False,
            citation_ids=answer.citation_ids,
        )
    return answer


def has_question_relevant_passage(question: str, passages: list[str]) -> bool:
    question_words = _WORD_PATTERN.findall(question.casefold())
    topic_terms: set[str] = set()
    for word in question_words:
        if word in _QUESTION_STOP_WORDS:
            continue
        matching_aliases = [
            aliases
            for prefix, aliases in _TOPIC_ALIASES.items()
            if word.startswith(prefix)
        ]
        if matching_aliases:
            for aliases in matching_aliases:
                topic_terms.update(aliases)
        elif len(word) >= 4:
            topic_terms.add(word[:6])

    if not topic_terms:
        return False
    if _TERMINATION_QUESTION.search(question) and any(
        _DURATION_LANGUAGE.search(passage) for passage in passages
    ):
        return True
    for passage in passages:
        passage_words = _WORD_PATTERN.findall(passage.casefold())
        if any(
            len(term) >= 4
            and any(word.startswith(term[:6]) or term.startswith(word[:6]) for word in passage_words)
            for term in topic_terms
        ):
            return True
    return False
