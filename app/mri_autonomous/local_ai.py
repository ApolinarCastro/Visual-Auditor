"""Local AI integration boundary for MRI (commercial-license safe).

No model is downloaded or loaded at import time. This module only documents and
validates the model/license contract and lazily builds a provider when the
operator supplies a local model file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class LocalAIUnavailable(RuntimeError):
    pass


class LocalAILicenseError(RuntimeError):
    pass


MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "granite-4.2-8b": {
        "family": "IBM Granite 4.2",
        "parameters": "8B",
        "license": "Apache-2.0",
        "commercial_allowed": True,
        "default_gguf": "models/granite-4.2-8b.gguf",
        "approx_q4_size_gb": 5,
    },
    "twil-8b": {
        "family": "TwIL",
        "parameters": "8B",
        "license": "Non-Commercial",
        "commercial_allowed": False,
        "default_gguf": None,
        "approx_q4_size_gb": 5,
    },
}


@dataclass(frozen=True)
class LocalAIConfig:
    model: str = "granite-4.2-8b"
    model_path: str = "models/granite-4.2-8b.gguf"
    backend: str = "llama_cpp"  # llama_cpp | transformers
    max_tokens: int = 512
    temperature: float = 0.1


def model_contract(model: str = "granite-4.2-8b") -> Dict[str, Any]:
    try:
        info = dict(MODEL_REGISTRY[model])
    except KeyError as exc:
        raise ValueError(f"Unknown local model: {model}") from exc
    if not info.get("commercial_allowed"):
        raise LocalAILicenseError(
            f"{model} license {info.get('license')} is not approved for commercial use")
    return info


def build_provider(config: Optional[LocalAIConfig] = None):
    """Lazily build a provider only if the local model file exists.

    llama-cpp-python and transformers are optional dependencies; neither is
    imported unless this function is called.
    """
    cfg = config or LocalAIConfig()
    info = model_contract(cfg.model)
    path = Path(cfg.model_path)
    if not path.is_file():
        raise LocalAIUnavailable(
            f"Local model not found: {path}. Download is intentionally not automated.")
    if cfg.backend == "llama_cpp":
        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as exc:
            raise LocalAIUnavailable("llama-cpp-python is not installed") from exc
        return Llama(model_path=str(path), n_ctx=4096, verbose=False)
    if cfg.backend == "transformers":
        try:
            from transformers import pipeline  # type: ignore
        except Exception as exc:
            raise LocalAIUnavailable("transformers is not installed") from exc
        return pipeline("text-generation", model=str(path))
    raise ValueError(f"Unsupported backend: {cfg.backend}")


def generate(prompt: str, config: Optional[LocalAIConfig] = None) -> str:
    cfg = config or LocalAIConfig()
    provider = build_provider(cfg)
    if cfg.backend == "llama_cpp":
        out = provider(prompt, max_tokens=cfg.max_tokens, temperature=cfg.temperature)
        return out["choices"][0]["text"]
    out = provider(prompt, max_new_tokens=cfg.max_tokens, temperature=cfg.temperature)
    return out[0]["generated_text"]
