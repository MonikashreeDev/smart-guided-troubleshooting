# Smart Guided Troubleshooting Engine

A runnable hackathon reference implementation for turning vague Galaxy complaints into validated, deeplinked troubleshooting plans.

## What is implemented

- Deterministic compiler pipeline: normalize -> retrieve SIIS evidence -> retrieve deeplink -> compile -> validate -> cache.
- Hybrid retrieval without external services: BM25-style lexical scoring plus feature-hashed character n-gram vectors.
- Separate SIIS and deeplink indexes. Masked URI strings are never searchable.
- Proof-carrying plans: each UI action shows its source evidence, chosen screen, scores, risk, and validator results.
- Strict contract and policy checks: wording, lengths, ordering, URL leakage, exact catalog membership, and source support.
- Exact cache and guarded semantic cache with domain, symptom, trigger, and feature agreement.
- Safe abstention on unsupported or ambiguous complaints.
- REST endpoints, evaluation endpoint, dashboard UI, and automated tests.

## Important asset note

The supplied PDF describes, but does not include, `queries.json`, `siis_responses.json`, `deeplinks.json`, `samples/`, or the original starter `schema.py`. This repository does **not** fabricate those files as official assets. Data under `data/demo_*.json` is clearly labeled synthetic and exists only so the project runs now. Replace it with the supplied hackathon assets before judging. The PDF's Appendix A contract is preserved in `engine/schema.py`; the Appendix B outer envelope is modeled separately in `engine/api_models.py` because the two shapes differ.

## Run

```bash
python3 app.py
# open http://127.0.0.1:8000
```

No third-party package is needed.

## API

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/v1/troubleshoot \
  -H 'Content-Type: application/json' \
  -d '{"query":"My phone became slow after an update"}'
curl -s http://127.0.0.1:8000/v1/metrics
```

Request: `query` plus optional `siis_response`. The response follows the worked-example envelope (`query`, `query_variations`, `response`, `meta`); `response` itself is exactly the Appendix A `ContextDeeplinkResponse` contract.

## Test

```bash
python3 -m unittest discover -s tests -v
python3 scripts/evaluate.py
```

## Replace demo data

1. Put the official files in `data/official/`.
2. Map SIIS rows to `{id, domain, title, text, keywords}`.
3. Map catalog rows to the Appendix A `Deeplink` fields plus a stable `id`.
4. Set `TROUBLESHOOT_DATA_DIR=data/official`.
5. Run tests and evaluation. The loader fails closed when required fields are missing.

## Demo script

1. Run `My phone became slow after an update` to show a cold compile, evidence, screen selection, and validators.
2. Run `Galaxy is laggy since I installed the latest software` to show guarded semantic reuse.
3. Run `My toaster is singing` to show safe abstention.
4. Open Metrics to show cache, latency, compliance, and retrieval measurements.
