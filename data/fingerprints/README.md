# Open-source reference fingerprint catalog

These are reference fingerprints for the verifier, in the same on-disk format as
`data/baselines/*.json` (consumed by `StatisticalAnalyzer.load_real_baselines`).

## Coverage (honest status, 2026-10-14)

| Model | Tokenizer fingerprint | Behavioral | How it was produced |
|---|---|---|---|
| `qwen2.5-0.5b-instruct` | **real** | not captured | Real prompt-token counts measured with the Qwen2.5-0.5B-Instruct tokenizer (downloaded via `HF_ENDPOINT=https://hf-mirror.com`). |
| `deepseek-r1-distill-qwen-1.5b` | **real (derived)** | not captured | Built on the Qwen2 tokenizer; counts equal Qwen's. Tokenizer repo was not separately re-downloaded (mirror refused repeated connections). Tokenizer probes alone cannot distinguish it from Qwen. |
| `glm-4-9b-chat` | **pending** | not captured | Model catalogued in `reference_server.CATALOG_TOKENIZERS`, but the GLM tokenizer could not be downloaded at build time (hf-mirror connection refused). It runs the reference-server in explicitly-labeled stub mode. |

## What is NOT here

- **No real generation / behavioral responses.** A local model was not run (torch/
  transformers + CPU inference was out of scope; see v2 notes). Behavioral
  reference distributions for open-source models should be sourced from the
  [Zenodo 165-model fingerprint dataset](https://zenodo.org/) (CC-BY-4.0, cited
  in `THIRD_PARTY_NOTICES.md`).
- **No closed-model fingerprints** (GPT/Claude/Gemini). Those require the user's
  own paid keys to collect; the verifier compares against whatever reference the
  operator provides.

## Re-collecting

```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
python -c "from tokenizers import Tokenizer; t=Tokenizer.from_pretrained('Qwen/Qwen2.5-0.5B-Instruct'); print(len(t.encode('Repeat this string exactly: a    b    c').ids))"
```

Deterministic tokenization -> identical samples.
