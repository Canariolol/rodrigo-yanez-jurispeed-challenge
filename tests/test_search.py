from jurispeed_challenge.search import search_jurisprudencia, search_normativa


def test_jurisprudencia_finds_arriendo(test_report) -> None:
    result = search_jurisprudencia("arrendatario lleva meses sin pagar renta", top_k=3)

    test_report.set_checked(
        "La busqueda de jurisprudencia encuentra evidencia relevante para arriendo impago."
    )
    test_report.set_setup(
        "Query='arrendatario lleva meses sin pagar renta', top_k=3."
    )
    test_report.set_observed(
        f"count={result['count']} y el primer resultado fue {result['results'][0]['id']}."
    )
    test_report.add_step("Tokeniza la consulta y compara overlap contra mock_data.json.")
    test_report.add_step("Ordena resultados por score y devuelve el rol mas relevante primero.")

    assert result["count"] >= 1
    assert result["results"][0]["id"] == "ROL-1234-2024"


def test_jurisprudencia_handles_missing_finiquito(test_report) -> None:
    result = search_jurisprudencia(
        "Corte Suprema nulidad de finiquito error calculo proporcional vacaciones",
        top_k=3,
    )

    test_report.set_checked(
        "La busqueda de jurisprudencia devuelve cero cuando el mock no tiene evidencia del tema."
    )
    test_report.set_setup(
        "Query='Corte Suprema nulidad de finiquito error calculo proporcional vacaciones', top_k=3."
    )
    test_report.set_observed(
        f"count={result['count']} y results={result['results']}."
    )
    test_report.add_step("Ejecuta la misma logica de ranking pero no supera el min_score.")
    test_report.add_step("Entrega una respuesta vacia para evitar alucinaciones aguas arriba.")

    assert result["count"] == 0
    assert result["results"] == []


def test_normativa_finds_rentas_no_percibidas(test_report) -> None:
    result = search_normativa("implicancias tributarias rentas no percibidas")

    first_code = result["results"][0]["codigo"] if result["results"] else "sin resultados"
    test_report.set_checked(
        "La busqueda normativa recupera reglas sobre rentas no percibidas desde el mock."
    )
    test_report.set_setup("Query='implicancias tributarias rentas no percibidas'.")
    test_report.set_observed(
        f"count={result['count']} y el primer codigo observado fue {first_code}."
    )
    test_report.add_step("Busca coincidencias en codigo y descripcion de normativa.")
    test_report.add_step("Confirma que la Circular SII relevante aparece entre los resultados.")

    assert result["count"] >= 1
    assert any("Circular SII" in item["codigo"] for item in result["results"])
