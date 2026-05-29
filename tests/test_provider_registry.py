from jurispeed_challenge.ai_providers import load_provider_registry


def test_provider_applies_override(monkeypatch, test_report) -> None:
    monkeypatch.setenv("GLOBAL_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("GLOBAL_AI_MODEL", "global-model")
    monkeypatch.setenv("JURISPEED_ORCHESTRATOR_MODEL", "orchestrator-model")

    registry = load_provider_registry(load_env_file=False)

    test_report.set_checked(
        "El registro de providers usa el override del orquestador por encima del modelo global."
    )
    test_report.set_setup(
        "GLOBAL_AI_PROVIDER=anthropic, GLOBAL_AI_MODEL=global-model, "
        "JURISPEED_ORCHESTRATOR_MODEL=orchestrator-model."
    )
    test_report.set_observed(
        "orchestrator.model=orchestrator-model y litigante.model=global-model."
    )
    test_report.add_step("Carga las variables de entorno y construye el registro por rol.")
    test_report.add_step("Compara el modelo resuelto para orchestrator contra litigante.")

    assert registry["orchestrator"].provider == "anthropic"
    assert registry["orchestrator"].model == "orchestrator-model"
    assert registry["litigante"].model == "global-model"
