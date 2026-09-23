# Architecture and judge-facing rationale

```text
Complaint
  -> AI understanding: Llama 3.3 70B (Workers AI) -> closed-vocabulary labels -> code-built canonical complaint
     (fallback: rules intent guard if AI is off, unsure, off-vocabulary or down)
  -> deterministic normalization + intent guard
  -> bge-small embedding domain match, only if rules find no domain (similarity >= 0.55, margin >= 0.06)
  -> L1 exact cache
  -> L2 semantic cache (bge-small cosine >= 0.90 AND domain/symptom/trigger/feature equality)
  -> hybrid SIIS index (BM25 + bge-small embeddings; hashed n-grams offline)
  -> evidence-bound action compiler
  -> separate hybrid deeplink metadata index
  -> child-screen confidence gate
  -> schema, source, URL, ordering and catalog validators
  -> immutable JSON cache / safe abstention
```

The model boundary is intentionally narrow: AI understands, code verifies.

- **LLM (Llama 3.3 70B Instruct, fp8-fast).** Reads the raw complaint in any language mix and returns JSON: supported, symptom, trigger, language, an English gloss and a confidence. `engine/ai.py` rejects anything outside the fixed symptom/trigger lists and ignores confidence below 0.6. Code, not the model, writes the canonical complaint that goes into retrieval. The model never produces steps, screens or URIs.
- **Embeddings (bge-small-en-v1.5).** Catalog and SIIS texts are embedded once at startup; queries are embedded per request. Scores blend BM25 (0.62) with rescaled cosine (0.38). A guarded embedding match can recover the domain when keyword rules find none.
- **Code owns** screen grouping, deeplink assignment, risk ordering, validation, serialization, and caching.
- **Fallback.** No credentials, a network error (one retry, then a 15 s circuit breaker), low confidence or off-vocabulary output all drop to the original deterministic path, which is still fully tested offline.
- **Cost.** Both models run on Cloudflare Workers AI's free daily allocation; no billing is enabled. About 1-2 s extra latency on a cold compile; exact cache hits skip the AI.

## Proof-carrying plan

Each plan records the SIIS source span, catalog record ID, screen identity, risk class, lexical/dense scores, and validator outcome. The public core response remains contract-exact; proof lives in the Appendix B metadata envelope.

## Failure behavior

Unsupported domain, weak SIIS match, weak deeplink match, or validator failure returns `{"contexts":[]}` with a machine-readable fallback reason. There is no fabricated recovery step or URI.

## Known limits

- Demo data is synthetic because official starter assets were absent from the supplied PDF attachment.
- The before/after benchmark (`data/eval_messy.json`, 33 cases: 75.8% -> 87.9% -> 100%) is a small synthetic set, not a production score.
- The Workers AI free tier has a daily neuron limit; past it the app falls back to the rules path until the daily reset.
- LLM output can vary slightly between runs; the closed vocabulary and validators keep that from reaching the plan.
- The PDF gives a core schema and a richer worked envelope. This project keeps both explicit instead of silently changing either.
