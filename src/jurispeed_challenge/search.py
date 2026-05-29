from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


MOCK_DATA_PATH = Path(__file__).resolve().parents[2] / "mock_data.json"

STOPWORDS = {
    "a",
    "al",
    "ante",
    "art",
    "con",
    "de",
    "del",
    "e",
    "el",
    "en",
    "es",
    "hay",
    "la",
    "las",
    "lo",
    "los",
    "mas",
    "mi",
    "no",
    "o",
    "por",
    "que",
    "se",
    "si",
    "sin",
    "sobre",
    "su",
    "un",
    "una",
    "y",
}


def load_mock_data(path: Path = MOCK_DATA_PATH) -> dict[str, list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return {
        "jurisprudencia": list(data.get("jurisprudencia", [])),
        "normativa": list(data.get("normativa", [])),
    }


def search_jurisprudencia(query: str, top_k: int = 3) -> dict[str, Any]:
    data = load_mock_data()
    results = _rank_records(
        records=data["jurisprudencia"],
        query=query,
        fields=("id", "tribunal", "extracto"),
        min_score=2,
        limit=top_k,
    )
    return {
        "source": "mock_data.json:jurisprudencia",
        "query": query,
        "count": len(results),
        "results": results,
    }


def search_normativa(query: str) -> dict[str, Any]:
    data = load_mock_data()
    results = _rank_records(
        records=data["normativa"],
        query=query,
        fields=("codigo", "descripcion"),
        min_score=1,
        limit=5,
    )
    return {
        "source": "mock_data.json:normativa",
        "query": query,
        "count": len(results),
        "results": results,
    }


def _rank_records(
    records: list[dict[str, Any]],
    query: str,
    fields: tuple[str, ...],
    min_score: int,
    limit: int,
) -> list[dict[str, Any]]:
    query_tokens = _tokenize(query)
    ranked: list[tuple[int, dict[str, Any]]] = []

    for record in records:
        record_text = " ".join(str(record.get(field, "")) for field in fields)
        record_tokens = _tokenize(record_text)
        score = _score(query_tokens, record_tokens)
        if score >= min_score:
            enriched_record = dict(record)
            enriched_record["score"] = score
            ranked.append((score, enriched_record))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [record for _, record in ranked[: max(limit, 0)]]


def _score(query_tokens: set[str], record_tokens: set[str]) -> int:
    return len(query_tokens & record_tokens)


def _tokenize(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]+", ascii_text)
    return {_stem(token) for token in tokens if len(token) > 2 and token not in STOPWORDS}


def _stem(token: str) -> str:
    suffixes = (
        "amientos",
        "imiento",
        "aciones",
        "adores",
        "adora",
        "amiento",
        "ibles",
        "adas",
        "ados",
        "ancia",
        "cion",
        "ciones",
        "ente",
        "idad",
        "ivas",
        "ivos",
        "mente",
        "renta",
        "rentas",
        "ario",
        "arios",
        "ada",
        "ado",
        "es",
        "os",
        "as",
    )
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) > len(suffix) + 3:
            return token[: -len(suffix)]
    return token

