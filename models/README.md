# Local AI models

MRI uses a commercial-license-safe local model boundary (`app.mri_autonomous.local_ai`).

## Approved

- **IBM Granite 4.2 8B** — Apache 2.0 — commercial use allowed.
- Expected GGUF: `models/granite-4.2-8b.gguf` (~5 GB Q4).
- Backends: `llama-cpp-python` (preferred) or `transformers`.
- The model is **not downloaded automatically** and is not loaded at import time.

## Rejected

- **TwIL-8B** — Non-Commercial license; not approved for commercial use.
- `local_ai.model_contract("twil-8b")` raises `LocalAILicenseError`.

## Usage

```python
from app.mri_autonomous.local_ai import LocalAIConfig, build_provider, generate

cfg = LocalAIConfig(model="granite-4.2-8b",
                    model_path="models/granite-4.2-8b.gguf",
                    backend="llama_cpp")
# build_provider(cfg) only works after the operator places the GGUF here.
```
