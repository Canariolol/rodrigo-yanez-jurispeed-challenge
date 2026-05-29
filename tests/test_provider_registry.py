from jurispeed_challenge.ai_providers import load_provider_registry


def test_provider_registry_reads_role_specific_overrides(monkeypatch) -> None:
    monkeypatch.setenv("GLOBAL_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("GLOBAL_AI_MODEL", "global-model")
    monkeypatch.setenv("JURISPEED_ORCHESTRATOR_MODEL", "orchestrator-model")

    registry = load_provider_registry(load_env_file=False)

    assert registry["orchestrator"].provider == "anthropic"
    assert registry["orchestrator"].model == "orchestrator-model"
    assert registry["litigante"].model == "global-model"
