# Taste (Continuously Learned by [CommandCode][cmd])
- Use InferHub as the default LLM provider with base URL `https://api.inferhub.dev/v1` and model `ocg/minimax-m3` (Minimax-M3). Confidence: 0.80
- Set `LLM_API_KEY`, `INFERHUB_API_KEY`, or `INFERHUB_KEY` to enable a live brain; without a key fall back to deterministic `StubClient`. Confidence: 0.75
- Spec-defined `role_weight` and `confidence_cap` from `ROLE_SPEC_DEFAULTS` must always be enforced on top of LLM model output (skeptic/risk capped at 0.35). Confidence: 0.85
- The `OpenAICompatClient` sends `response_format: {"type": "json_object"}` with `temperature: 0.0` for structured JSON opinions. Confidence: 0.70
- InferHub endpoint `https://api.inferhub.dev/v1` is OpenAI-compatible and resolves `ocg/minimax-m3`. Confidence: 0.90
- Validate InferHub keys via `npx @inferhub/helper validate --key <key>`; the helper checks against `GET /v1/models`. Confidence: 0.65
