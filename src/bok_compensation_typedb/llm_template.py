"""Shared LLM configuration for Ollama and OpenAI-compatible backends."""

import os
from typing import Any, List


DEFAULT_OLLAMA_MODEL = "your-ollama-model-name"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_EMBEDDING_MODEL = "your-ollama-embedding-model"
DEFAULT_OPENAI_MODEL = "your-openai-model-name"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


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


def get_embedding_model_name() -> str:
    if get_llm_provider() == "ollama":
        return os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL)
    return os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL)


def create_chat_model(*, temperature: float = 0.0, json_output: bool = False) -> Any:
    provider = get_llm_provider()
    model_name = get_llm_model_name()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        model = ChatOllama(
            model=model_name,
            base_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL),
            temperature=temperature,
        )
        if json_output:
            return model.bind(format="json")
        return model

    if provider == "openai-compatible":
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=model_name,
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here"),
            temperature=temperature,
            max_tokens=2048,
        )
        if json_output:
            return model.bind(response_format={"type": "json_object"})
        return model

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def create_qwen_model(*, temperature: float = 0.0) -> Any:
    """Qwen DB query sub-agent용 모델. QWEN_* 환경변수 우선, 없으면 OPENAI_* 폴백."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.getenv("QWEN_MODEL", get_llm_model_name()),
        base_url=os.getenv("QWEN_BASE_URL", os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)),
        api_key=os.getenv("QWEN_API_KEY", os.getenv("OPENAI_API_KEY", "your-api-key-here")),
        temperature=temperature,
        max_tokens=2048,
    )


def create_embedding_model() -> Any:
    provider = get_llm_provider()
    model_name = get_embedding_model_name()

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=model_name,
            base_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL),
        )

    if provider == "openai-compatible":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model_name,
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here"),
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def embed_text(text: str) -> List[float]:
    model = create_embedding_model()
    if hasattr(model, "embed_query"):
        return list(model.embed_query(text))
    documents = model.embed_documents([text])
    return list(documents[0]) if documents else []