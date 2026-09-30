# Design decisions

## Candidate evidence is immutable

Chunking recognizes Markdown section headings and splits nonempty lines into bounded, overlapping windows. Every window keeps its section, stable content/offset ID, and Python Unicode character offsets. Suggested resume excerpts are copied verbatim from these windows. This conservative approach can reorder evidence but cannot rewrite a bullet, invent a metric, or assert an unsupported skill. It verifies provenance, not truth.

## Explainable two-part rank

Each request creates its own in-memory Qdrant collection. Experience chunks are embedded once. Each job queries all chunks, ordered by cosine similarity. Requirement matching selects the highest-ranked chunk that explicitly mentions the skill and passes a conservative negation filter. The displayed rank is `100 × (0.75 × coverage + 0.25 × max(0, cosine))`, clamped to the natural score bounds. Jobs with zero recognized requirements receive zero instead of a misleading perfect score.

The default encoder uses signed SHA-256 feature hashing with weighted skill aliases in 384 dimensions. It has no trained language understanding. The optional FastEmbed adapter uses BGE-small; its runtime/model download is independent of the reproducible demo. Neither score is calibrated against hiring outcomes.

## Collection stays out of the public API

The CLI collector accepts at most 100 URLs and 1–8 concurrent workers. Exact host allowlists, public-address checks, HTTPS-only URLs, robots policy, per-host serialization, timeouts, limited retries, and content deduplication bound its behavior. JSON-LD JobPosting is preferred; readable page text is the fallback. Each result includes a source URL; individual failures do not discard successful jobs.

It deliberately blocks cross-host assets and redirected navigation. That reduces compatibility. DNS validation is not an egress firewall and does not completely prevent DNS rebinding. Use trusted URLs on a controlled machine; do not expose collection to anonymous users. There is no CAPTCHA bypass, login support, automated discovery, application submission, or scale validation. Network/page size limits and distributed queues are future work.

## Structured extraction is not truth verification

Rules detect a small skill ontology. Instructor is an optional CLI-only extraction path: Pydantic validates the output shape, then a separate deterministic check rejects invented quotes, duplicate skills, negated requirements, and labels not supported by the quote. Prompt injection remains a risk for a model, but extraction has no tools or side effects, and it cannot change resume evidence. The model receives job text only.

## Privacy and operating boundary

The default app calls no third-party API, saves no resumes, uses no browser storage, and closes each Qdrant client after matching. Request values are not deliberately logged. Run the server on loopback. There is no authentication, persistent user store, audit trail, durable queue, or production ingress/rate limiting. Field and total-text limits constrain valid requests; a production gateway must cap raw request sizes and concurrent connections. The two-slot semaphore bounds matching work per server process, not distributed traffic.

## Next steps

1. Build a labeled relevance set and evaluate retrieval independently of the four demo fixtures.
2. Add source-specific permitted adapters, page-size budgets, and network egress isolation.
3. Add semantic-adapter integration coverage using a pinned model revision/cache.
4. Support reviewed paraphrases with sentence-level entailment checks, while preserving original excerpts.
5. Add authenticated sessions, encrypted persistence, and a documented retention policy before hosting real resumes.
