"""Shared LLM configuration for Ollama and OpenAI-compatible backends."""

import os
from typing import Any


DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:14b-instruct"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OPENAI_MODEL = "HCX-GOV-THINK-V1-32B"
DEFAULT_OPENAI_BASE_URL = "http://211.188.81.250:30402/v1"


def get_llm_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "openai-compatible").strip().lower()
    aliases = {
        "openai": "openai-compatible",
        "openai_compatible": "openai-compatible",
        "compat": "openai-compatible",
    }
    return aliases.get(provider, provider)


def get_llm_model_name() -> str:
    if get_llm_provider() == "ollama":
        return os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def create_chat_model(*, temperature: float = 0.0, json_output: bool = False) -> Any:
    provider = get_llm_provider()
    model_name = get_llm_model_name()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs = {
            "model": model_name,
            "base_url": os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL),
            "temperature": temperature,
        }
        if json_output:
            kwargs["format"] = "json"
        return ChatOllama(**kwargs)

    if provider == "openai-compatible":
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=model_name,
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            api_key=os.getenv("OPENAI_API_KEY", "unused"),
            temperature=temperature,
        )
        if json_output:
            return model.bind(response_format={"type": "json_object"})
        return model

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")