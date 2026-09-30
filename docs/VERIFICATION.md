# Verification record

Verification date: September 29, 2026 (America/New_York). Python 3.11 on Windows. The workflow repeats the checks on Ubuntu; use the linked GitHub Actions run for current remote status.

## Evidence scope

The bundled candidate, jobs, and HTML page are original synthetic fixtures. They test program behavior and provenance, not job-market performance or recruiter outcomes. Dependencies used for local verification are constrained in `constraints.txt`; transitive dependencies are not fully locked.

## Reproducible checks

- Editable installation with declared extras and isolated build tooling.
- Ruff lint and formatting checks.
- Pytest behavior checks including source offsets, ranking, negation, isolation, extraction validation, concurrency, retry, failure handling, and URL/robots policy.
- Chromium rendering of the bundled job page.
- `scripts/browser_check.py`: real local HTTP server and Chromium UI checks for matching, source inspection, Markdown download, 390-pixel layout, invalid JSON recovery, and untrusted markup rendering.
- CLI synthetic demo output, saved to `work/demo-result.json`.

## Recorded local results

| Check | Result |
| --- | --- |
| Editable package installation | Passed with `.[dev,browser,llm]` and constraints |
| Ruff lint / format | Passed |
| Full pytest suite | **26 passed** in 49.65 seconds, including actual Chromium fixture rendering |
| Live dashboard browser check | Passed: ranking, evidence, export, mobile, error recovery, safe text rendering |
| CLI demo | Produced four ranked roles from five source chunks |

The test duration is one local observation, not a performance benchmark. Windows sandbox restrictions initially blocked Playwright subprocess pipes; Chromium checks passed when run outside that sandbox. No application behavior was weakened to bypass a failing test.

### Synthetic fixture results

| Role | Rank / 100 | Extracted skill coverage | Missing evidence |
| --- | ---: | ---: | --- |
| Backend Engineer | 92.51 | 100% | None among extracted skills |
| Frontend Engineer | 87.06 | 100% | None among extracted skills |
| Search Platform Engineer | 68.25 | 66.67% | Kubernetes, AWS |
| Machine Learning Engineer | 22.31 | 20% | Kubernetes, AWS, machine learning, PyTorch |

Regression tests distinguish “machine learning” from a learning goal and preserve whitespace/Unicode source offsets. The learning-goal line does not count as Kubernetes experience. Every emitted excerpt is an exact slice of the validated input document.

Captured by the actual browser check: [desktop](screenshots/dashboard.png), [mobile](screenshots/mobile.png). The screenshots show synthetic data only. GitHub CI repeats the checks on Linux and stores fresh screenshots as workflow artifacts.

## Intentionally unverified

- Real career-portal compatibility and actual robots responses. Browser collection policy is checked with controlled transport/browser doubles; fixture rendering and the dashboard use real Chromium.
- Instructor provider network call and model extraction quality. The adapter's configuration and quote-verification path are checked with a stubbed provider.
- FastEmbed model download/inference and neural relevance quality.
- Persistent/remote Qdrant operations, multi-user isolation under load, and production hosting.
- Hundreds-of-sites scalability, search quality on a labeled corpus, hiring outcomes, and fairness.

## Publication hygiene

Only source, tests, fictional fixtures, documentation, screenshots, license, and CI configuration belong in Git. Local environments, working files, user outputs, caches, editable-install metadata, and secret environment files are excluded. Source excerpts shown in screenshots and generated review notes belong to fictional Alex Morgan.
