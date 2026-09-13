from services.api.shuddho_api.llm_provider import DEFAULT_DEEPSEEK_MODEL, DEFAULT_GEMMA_MODEL, resolve_llm_config


def test_default_runtime_is_deepseek_with_configurable_model() -> None:
    config = resolve_llm_config({"DEEPSEEK_API_KEY": "test-only-placeholder"})
    assert config.provider == "deepseek"
    assert config.model == DEFAULT_DEEPSEEK_MODEL
    assert config.configured is True
    assert "test-only-placeholder" not in repr(config)
    override = resolve_llm_config({"DEEPSEEK_MODEL": "deepseek-v4-pro", "DEEPSEEK_API_KEY": "test-only-placeholder"})
    assert override.model == "deepseek-v4-pro"


def test_explicit_gemma_runtime_remains_available_for_rollback() -> None:
    config = resolve_llm_config({"SHUDDHO_LLM_PROVIDER": "gemma", "GOOGLE_API_KEY": "test-only-placeholder"})
    assert config.provider == "gemma"
    assert config.model == DEFAULT_GEMMA_MODEL == "gemma-4-26b-a4b-it"
    assert config.configured is True


def test_explicit_forbidden_providers_fail_closed() -> None:
    for provider in ("openai", "openrouter", "qwen", "gemini", "anything-else"):
        config = resolve_llm_config({"SHUDDHO_LLM_PROVIDER": provider, "GOOGLE_API_KEY": "placeholder"})
        assert config.enabled is False
        assert config.configured is False
        assert config.status == "unsupported_provider"


def test_gemini_model_and_missing_key_are_reported_safely() -> None:
    rejected = resolve_llm_config({"SHUDDHO_LLM_PROVIDER": "gemma", "GEMMA_MODEL": "gemini-2.5-flash", "GOOGLE_API_KEY": "placeholder"})
    assert rejected.status == "unsupported_provider"
    missing = resolve_llm_config({"SHUDDHO_LLM_PROVIDER": "gemma", "SHUDDHO_ENABLE_LLM": "true"})
    assert missing.status == "missing_key"
    assert missing.api_key is None


def test_deepseek_never_uses_a_google_key_or_an_unrelated_model() -> None:
    missing = resolve_llm_config({"GOOGLE_API_KEY": "test-only-placeholder", "SHUDDHO_ENABLE_LLM": "true"})
    assert missing.provider == "deepseek"
    assert missing.api_key is None
    assert missing.status == "missing_key"
    assert missing.warnings == ["deepseek_api_key_missing"]
    rejected = resolve_llm_config({"DEEPSEEK_MODEL": "gemma-anything", "DEEPSEEK_API_KEY": "test-only-placeholder"})
    assert rejected.status == "unsupported_provider"
