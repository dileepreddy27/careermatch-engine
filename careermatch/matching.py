import hashlib
import math
import re
from collections.abc import Callable

from qdrant_client import QdrantClient, models

from .chunking import chunk_document
from .extraction import SKILLS, extract_rules, supports
from .models import Evidence, JobMatch, MatchRequest, MatchResponse, RequirementMatch


class DemoEmbedding:
    """Deterministic signed feature hashing; NOT a trained semantic embedding."""

    name = "demo-hash-384"
    size = 384

    def encode(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            tokens = re.findall(r"[a-z0-9]+", text.casefold())
            tokens += ["skill:" + s for s in SKILLS if supports(text, s)] * 3
            vector = [0.0] * self.size
            for token in tokens:
                digest = hashlib.sha256(token.encode()).digest()
                vector[int.from_bytes(digest[:4], "big") % self.size] += 1 if digest[4] % 2 else -1
            norm = math.sqrt(sum(v * v for v in vector)) or 1
            result.append([v / norm for v in vector])
        return result


class SemanticEmbedding:
    name = "BAAI/bge-small-en-v1.5"
    size = 384

    def __init__(self):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "Install careermatch-engine[semantic]; model download required"
            ) from exc
        self.model = TextEmbedding(model_name=self.name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.embed(texts)]


def match(
    request: MatchRequest, embedding=None, extractor: Callable = extract_rules
) -> MatchResponse:
    embedding = embedding or DemoEmbedding()
    chunks = chunk_document(request.resume)
    if not chunks:
        raise ValueError("Resume contains no experience text")
    if len(chunks) > 500:
        raise ValueError("Resume exceeds the 500-chunk review limit")
    # Per-request index: no cross-candidate leakage or stale vectors.
    client = QdrantClient(location=":memory:")
    try:
        client.create_collection(
            "experience",
            vectors_config=models.VectorParams(
                size=embedding.size,
                distance=models.Distance.COSINE,
            ),
        )
        client.upsert(
            "experience",
            points=[
                models.PointStruct(id=i, vector=v)
                for i, v in enumerate(embedding.encode([c.text for c in chunks]))
            ],
        )
        matches = []
        queries = embedding.encode([job.title + "\n" + job.text for job in request.jobs])
        for job, query in zip(request.jobs, queries, strict=True):
            hits = client.query_points("experience", query=query, limit=len(chunks)).points
            requirements = extractor(job).requirements
            rows = []
            excerpts = {}
            for requirement in requirements:
                evidence = None
                for hit in hits:
                    chunk = chunks[int(hit.id)]
                    if supports(chunk.text, requirement.skill):
                        evidence = Evidence(
                            chunk_id=chunk.id,
                            section=chunk.section,
                            quote=chunk.text,
                            start=chunk.start,
                            end=chunk.end,
                        )
                        # Excerpts are verbatim; no generative edits can introduce claims.
                        assert request.resume[evidence.start : evidence.end] == evidence.quote
                        excerpts[evidence.chunk_id] = evidence
                        break
                rows.append(
                    RequirementMatch(
                        skill=requirement.skill,
                        job_quote=requirement.quote,
                        status="supported" if evidence else "gap",
                        evidence=evidence,
                    )
                )
            coverage = sum(r.status == "supported" for r in rows) / len(rows) if rows else 0
            similarity = max(0.0, min(1.0, hits[0].score)) if hits else 0
            score = (0.75 * coverage + 0.25 * similarity) if rows else 0
            matches.append(
                JobMatch(
                    id=job.id,
                    title=job.title,
                    company=job.company,
                    source=job.source,
                    rank_score=round(score * 100, 2),
                    vector_similarity=round(similarity, 4),
                    coverage=round(coverage, 4),
                    requirements=rows,
                    suggested_excerpts=list(excerpts.values()),
                    gaps=[r.skill for r in rows if not r.evidence],
                )
            )
        return MatchResponse(
            mode=embedding.name,
            extraction=extractor.__name__,
            chunks=len(chunks),
            disclaimer="Scores are ranking heuristics, not hiring probabilities. Source-linked "
            "excerpts verify text provenance only, not truth or proficiency. "
            "Review every suggestion.",
            matches=sorted(matches, key=lambda m: (-m.rank_score, m.id)),
        )
    finally:
        client.close()
