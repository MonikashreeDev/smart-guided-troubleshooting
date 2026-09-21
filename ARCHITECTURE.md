# Architecture and judge-facing rationale

```text
Complaint
  -> deterministic normalization + intent guard
  -> L1 exact cache
  -> L2 semantic cache (vector threshold AND domain/symptom/trigger/feature equality)
  -> hybrid SIIS index (BM25 + feature-hashed character n-grams)
  -> evidence-bound action compiler
  -> separate hybrid deeplink metadata index
  -> child-screen confidence gate
  -> schema, source, URL, ordering and catalog validators
  -> immutable JSON cache / safe abstention
```

The model boundary is intentionally narrow. A production adapter may use an LLM to normalize complaints and extract candidate actions, but normal code owns screen grouping, deeplink assignment, risk ordering, validation, serialization, and caching. This demo stays offline and deterministic so it is inspectable and reproducible.

## Proof-carrying plan

Each plan records the SIIS source span, catalog record ID, screen identity, risk class, lexical/dense scores, and validator outcome. The public core response remains contract-exact; proof lives in the Appendix B metadata envelope.

## Failure behavior

Unsupported domain, weak SIIS match, weak deeplink match, or validator failure returns `{"contexts":[]}` with a machine-readable fallback reason. There is no fabricated recovery step or URI.

## Known limits

- Demo data is synthetic because official starter assets were absent from the supplied PDF attachment.
- Feature-hashed n-grams are deterministic and lightweight, but production should plug in the hackathon embedding model.
- The PDF gives a core schema and a richer worked envelope. This project keeps both explicit instead of silently changing either.
