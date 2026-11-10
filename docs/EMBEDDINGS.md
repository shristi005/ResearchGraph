# Embeddings
Separate from chat generation and from storage (Supabase stores/searches; it does not embed).
Old system: Ollama `nomic-embed-text` (768-d, JSON in SQLite, cosine in Python). Ollama cannot run in the deployment.

| Option | Quality | Fits free hosting? | Status here |
|---|---|---|---|
| `gemini` (Gemini embedding API, `outputDimensionality=768`, L2-normalised) — **default** | strong general retrieval (unverified on your papers) | yes, no RAM; counts against Gemini free quota; verify limits | implemented; contract tested against a stand-in only |
| `local` (fastembed ONNX, `nomic-ai/nomic-embed-text-v1.5`, 768-d) | closest to the old model | needs ~0.5–1 GB RAM: not on Render free; fine locally/bigger host | implemented, optional dep, untested |
| `hash` | toy | yes | tests/offline demo only |
| Ollama in cloud | — | no | removed |
No paid embedding API is included. I could not call any embedding service from the authoring sandbox, so **retrieval quality is unmeasured**: run `live_check.py` (dimension, ranking) and the Mentor benchmark.

## Consistency rules implemented
- Every vector records `provider:model:dim` (`chunks.embed_model`, paper JSON `model`). Retrieval only searches vectors of the current model; mismatched ones are ignored and re-embedded automatically on next use (new vectors are created before old ones are replaced).
- 768 is fixed in SQL (`vector(768)`), so switching between the three providers needs no schema change. A different dimension needs a new migration + re-embedding.
- Old SQLite/nomic vectors are **not** imported (different model); they regenerate lazily.
- **Similarity thresholds are model-specific.** `RG_SIM_THRESHOLD=0.70` was tuned for nomic. Gemini cosine scores sit on a different scale: re-tune on the six-paper benchmark (target: 4 music papers connected, 2 inspection papers connected, no music↔inspection semantic edge). Until then the graph may have too many or too few semantic edges.
