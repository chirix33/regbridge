import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from app.domain.models import EvidenceSpan
from app.evaluation.models import RetrievalHit, RetrievalTrace

TOKEN_PATTERN = re.compile(r"\d+(?:\.[a-z0-9]+)+|[^\W_]+", re.UNICODE)
BM25_CONFIGURATION = {
    "name": "dependency-free-bm25",
    "top_k": 3,
    "k1": 1.5,
    "b": 0.75,
    "idf_formula": "log(1+(N-df+0.5)/(df+0.5))",
    "tokenization": "NFKC-casefold-preserve-dotted-ctd-identifiers",
    "tie_break": "evidence-id-ascending",
}


def tokenize(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(TOKEN_PATTERN.findall(normalized))


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class BM25Retriever:
    corpus: tuple[EvidenceSpan, ...]
    top_k: int = 3
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        if (self.top_k, self.k1, self.b) != (3, 1.5, 0.75):
            raise ValueError("M3 BM25 configuration is frozen at top_k=3, k1=1.5, b=0.75")
        if len({item.id for item in self.corpus}) != len(self.corpus):
            raise ValueError("BM25 evidence identifiers must be unique")
        if len(self.corpus) < self.top_k:
            raise ValueError("BM25 corpus is smaller than top_k")
        if tuple(item.id for item in self.corpus) != tuple(sorted(item.id for item in self.corpus)):
            raise ValueError("BM25 corpus must use evidence-ID ordering")

    @property
    def corpus_sha256(self) -> str:
        payload = [item.model_dump(mode="json") for item in self.corpus]
        return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()

    @property
    def configuration_sha256(self) -> str:
        configuration = {**BM25_CONFIGURATION, "corpus_sha256": self.corpus_sha256}
        return hashlib.sha256(_canonical(configuration).encode("utf-8")).hexdigest()

    def retrieve(self, *, case_id: str, query: str) -> RetrievalTrace:
        documents = [tokenize(f"{item.locator} {item.text}") for item in self.corpus]
        query_tokens = tokenize(query)
        document_count = len(documents)
        average_length = sum(len(document) for document in documents) / document_count
        document_frequency = Counter(token for document in documents for token in set(document))
        scores: list[tuple[str, float]] = []
        for span, document in zip(self.corpus, documents, strict=True):
            frequencies = Counter(document)
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if not frequency:
                    continue
                df = document_frequency[token]
                idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * len(document) / average_length
                )
                score += idf * (frequency * (self.k1 + 1)) / denominator
            scores.append((span.id, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        hits = tuple(
            RetrievalHit(evidence_id=evidence_id, score=score, rank=rank)
            for rank, (evidence_id, score) in enumerate(scores[: self.top_k], start=1)
        )
        return RetrievalTrace(
            case_id=case_id,
            query=query,
            query_sha256=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            corpus_sha256=self.corpus_sha256,
            configuration_sha256=self.configuration_sha256,
            top_k=3,
            k1=1.5,
            b=0.75,
            idf_formula="log(1+(N-df+0.5)/(df+0.5))",
            hits=hits,
        )
