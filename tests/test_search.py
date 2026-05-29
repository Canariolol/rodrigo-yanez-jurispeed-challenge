from jurispeed_challenge.search import search_jurisprudencia, search_normativa


def test_search_jurisprudencia_finds_arriendo_records() -> None:
    result = search_jurisprudencia("arrendatario lleva meses sin pagar renta", top_k=3)

    assert result["count"] >= 1
    assert result["results"][0]["id"] == "ROL-1234-2024"


def test_search_jurisprudencia_returns_zero_for_unrelated_finiquito_query() -> None:
    result = search_jurisprudencia(
        "Corte Suprema nulidad de finiquito error calculo proporcional vacaciones",
        top_k=3,
    )

    assert result["count"] == 0
    assert result["results"] == []


def test_search_normativa_finds_rentas_no_percibidas() -> None:
    result = search_normativa("implicancias tributarias rentas no percibidas")

    assert result["count"] >= 1
    assert any("Circular SII" in item["codigo"] for item in result["results"])

