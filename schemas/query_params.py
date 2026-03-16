from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator


def _coerce_csv_tokens(value: Any) -> list[str]:
    if value is None or value == "":
        return []

    raw_items = value if isinstance(value, list) else [value]
    tokens: list[str] = []
    for item in raw_items:
        if item is None or item == "":
            continue
        if isinstance(item, str):
            parts = item.split(",")
        else:
            parts = [str(item)]
        tokens.extend(part.strip() for part in parts if part and part.strip())
    return tokens


def _parse_csv_int_list(value: Any) -> list[int]:
    tokens = _coerce_csv_tokens(value)
    parsed: list[int] = []
    for token in tokens:
        try:
            parsed.append(int(token))
        except ValueError as exc:
            raise ValueError(f"Invalid integer value: {token}") from exc
    return parsed


def _parse_csv_str_list(value: Any) -> list[str]:
    return _coerce_csv_tokens(value)


CsvIntList = Annotated[list[int], BeforeValidator(_parse_csv_int_list)]
CsvStrList = Annotated[list[str], BeforeValidator(_parse_csv_str_list)]
