# Smart Guided Troubleshooting Engine

A runnable hackathon reference implementation for turning vague Galaxy complaints into validated, deeplinked troubleshooting plans.

## What is implemented

- **AI complaint understanding.** An open-source LLM, **Llama 3.3 70B Instruct (fp8-fast)** on Cloudflare Workers AI, reads messy complaints (English paraphrases, Hinglish, Tanglish, typos) and maps them onto the engine's closed symptom vocabulary. It never writes steps or links. Code validates its labels, builds a canonical complaint, and the deterministic pipeline does the rest. Low confidence, off-vocabulary output or an outage falls back to the rules path.
- **Real embeddings.** **BAAI bge-small-en-v1.5** on Workers AI replaces the hashed n-gram vectors for SIIS search, deeplink search, the semantic cache, and a guarded domain match when keyword rules find nothing. Hashed n-grams remain the offline fallback.
- AI understands, code verifies: every plan still passes the same schema, source-support, ordering, URL and catalog validators.
- Compiler pipeline: understand -> normalize -> retrieve SIIS evidence -> retrieve deeplink -> compile -> validate -> cache.
- Hybrid retrieval: BM25-style lexical scoring plus dense vectors (bge-small when available, feature-hashed character n-grams offline).
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

No third-party package is needed. Without credentials the app runs fully offline on the deterministic path.

To turn the AI layer on (Cloudflare Workers AI free tier, no billing needed):

```bash
export CF_ACCOUNT_ID=<your Cloudflare account id>
export CF_API_TOKEN=<API token with Workers AI permission>
python3 app.py
```

Optional: `SGT_AI=off` forces the rules path; `SGT_AI_MIN_CONFIDENCE` (default 0.6) sets how sure the LLM must be.

## Benchmark: before and after AI

`python3 scripts/evaluate_ai.py` runs 33 messy complaints (`data/eval_messy.json`: clean English, English paraphrases, Hinglish, Tanglish, typos, out-of-scope) cold, with caches cleared. A case is correct when the right catalog screen is returned, or when an out-of-scope complaint safely abstains.

| Configuration | Accuracy | Wrong plans |
|---|---|---|
| Before: rules + hashed n-grams | 75.8% (25/33) | 0 |
| + bge-small embeddings | 87.9% (29/33) | 0 |
| + Llama 3.3 70B complaint understanding | 100% (33/33) | 0 |

The evaluation set is synthetic and small, written for this prototype, so treat it as a demo benchmark rather than a production score. Results are saved to `evaluation_ai.json` and shown on the dashboard.

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
python3 -m unittest discover -s tests -v   # offline; the AI layer is tested with a fake client
python3 scripts/evaluate.py
python3 scripts/evaluate_ai.py               # needs CF_ACCOUNT_ID and CF_API_TOKEN
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
3. Run the Tanglish example `mobile romba hang aagudhu, app open panna time edukudhu` to show AI understanding: the rules alone abstain on it, the LLM maps it to "slow", and validators still check the plan.
4. Run `My toaster is singing` to show safe abstention.
5. Show the metrics panel: cache, latency, AI status and the before/after benchmark.

## AI usage

- Runtime models: Llama 3.3 70B Instruct (fp8-fast, `@cf/meta/llama-3.3-70b-instruct-fp8-fast`) for complaint understanding and BAAI bge-small-en-v1.5 (`@cf/baai/bge-small-en-v1.5`) for embeddings, both open-source and served by Cloudflare Workers AI on its free tier.
- The LLM only returns labels from a fixed list. Troubleshooting steps and deeplinks come from SIIS evidence and the catalog, never from the model.
- Development of this prototype was AI-assisted (code generation and documentation drafting), reviewed and tested by the team.
