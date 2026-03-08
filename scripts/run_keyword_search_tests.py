from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import httpx


DEFAULT_QUERIES: list[dict[str, Any]] = [
    {"query": "гололедица"},
    {"query": "пожар"},
    {"query": "температура"},
    {"query": "квартира"},
    {"query": "стоимость"},
    {"query": "штраф"},
    {"query": "уголовное"},
    {"query": "белавиа"},
    {"query": "мчс"},
    {"query": "минск"},
    {"query": "брест"},
    {"query": "гомель"},
    {"query": "витебск"},
    {"query": "оранжевый уровень"},
    {"query": "уровень опасности"},
    {"query": "уголовное дело"},
    {"query": "температура воздуха"},
    {"query": "минск мир"},
    {"query": "стоимость квадратного метра"},
    {"query": "белорусский рубль"},
]


@dataclass
class QueryResult:
    query: str
    filters: str
    took_ms: int
    total: int
    top10_post_ids: list[int]
    expected_post_ids: list[int]
    hits_at_10: int
    precision_at_10: float
    notes: str = ""


def _quantile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    values_sorted = sorted(values)
    idx = (len(values_sorted) - 1) * q
    lower = int(idx)
    upper = min(lower + 1, len(values_sorted) - 1)
    weight = idx - lower
    return values_sorted[lower] * (1.0 - weight) + values_sorted[upper] * weight


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run POST /api/keyword/search/posts tests and save summary to docs/*.txt",
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", help="Login username (local auth)")
    parser.add_argument("--password", help="Login password (local auth)")
    parser.add_argument("--token", help="Bearer token. If set, login step is skipped.")
    parser.add_argument(
        "--queries-file",
        help="Optional JSON file with queries. Format: [{\"query\":\"...\",\"expected_post_ids\":[1,2]}]",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--date-from", help="ISO datetime, example: 2026-02-04T00:00:00Z")
    parser.add_argument("--date-to", help="ISO datetime, example: 2026-03-04T23:59:59Z")
    parser.add_argument("--channel-ids", help="CSV channel ids, example: 2,9,10,11")
    parser.add_argument(
        "--output",
        help="Output path. Default: docs/keyword_search_test_results_<timestamp>.txt",
    )
    return parser.parse_args()


def _load_queries(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return DEFAULT_QUERIES
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("queries-file must contain JSON array")
    out: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("query"), str):
            continue
        expected = item.get("expected_post_ids", [])
        if not isinstance(expected, list):
            expected = []
        out.append({"query": item["query"], "expected_post_ids": [int(x) for x in expected]})
    if not out:
        raise ValueError("queries-file does not contain valid queries")
    return out


def _parse_channel_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        out.append(int(token))
    return out


def _build_filters_label(*, date_from: str | None, date_to: str | None, channel_ids: list[int]) -> str:
    parts: list[str] = []
    if date_from:
        parts.append(f"date_from={date_from}")
    if date_to:
        parts.append(f"date_to={date_to}")
    if channel_ids:
        parts.append(f"channel_ids={channel_ids}")
    return "; ".join(parts)


def _auth_token(client: httpx.Client, *, base_url: str, token: str | None, username: str | None, password: str | None) -> str:
    if token:
        return token
    if not username or not password:
        raise ValueError("Provide either --token or --username/--password")
    resp = client.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("access_token not found in login response")
    return str(access_token)


def _render_report(
    *,
    now_iso: str,
    base_url: str,
    channel_ids: list[int],
    date_from: str | None,
    date_to: str | None,
    results: list[QueryResult],
) -> str:
    took_values = [item.took_ms for item in results]
    total_values = [item.total for item in results]
    errors_count = sum(1 for item in results if item.notes)
    queries_with_expected = sum(1 for item in results if item.expected_post_ids)

    lines: list[str] = []
    lines.append("# Keyword Search API Test Results")
    lines.append("")
    lines.append(f"- Generated at (UTC): {now_iso}")
    lines.append(f"- Base URL: {base_url}")
    lines.append(f"- Filters: {_build_filters_label(date_from=date_from, date_to=date_to, channel_ids=channel_ids) or 'none'}")
    lines.append("")
    lines.append("## 2.1 Query Set Summary")
    lines.append(f"- Total queries tested: {len(results)}")
    lines.append(f"- Queries with expected results: {queries_with_expected}")
    lines.append(f"- Avg took_ms: {round(mean(took_values), 2) if took_values else 0}")
    lines.append(f"- p50 took_ms: {round(_quantile(took_values, 0.50), 2) if took_values else 0}")
    lines.append(f"- p95 took_ms: {round(_quantile(took_values, 0.95), 2) if took_values else 0}")
    lines.append(f"- Max took_ms: {max(took_values) if took_values else 0}")
    lines.append(f"- Avg total results: {round(mean(total_values), 2) if total_values else 0}")
    lines.append(f"- Errors (4xx/5xx) count: {errors_count}")
    lines.append("")
    lines.append("## 2.2 Per-query Results (top-10)")
    lines.append("| # | query | filters | took_ms | total | top10_post_ids | expected_post_ids | hits@10 | precision@10 | notes |")
    lines.append("|---|-------|---------|---------|-------|----------------|-------------------|---------|--------------|-------|")
    filter_label = _build_filters_label(date_from=date_from, date_to=date_to, channel_ids=channel_ids)
    for idx, item in enumerate(results, start=1):
        lines.append(
            f"| {idx} | {item.query} | {filter_label} | {item.took_ms} | {item.total} | "
            f"{item.top10_post_ids} | {item.expected_post_ids} | {item.hits_at_10} | "
            f"{item.precision_at_10:.2f} | {item.notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    queries = _load_queries(args.queries_file)
    channel_ids = _parse_channel_ids(args.channel_ids)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d%H%M%S")
    output_path = Path(args.output) if args.output else Path("docs") / f"keyword_search_test_results_{timestamp}.txt"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        token = _auth_token(
            client,
            base_url=args.base_url.rstrip("/"),
            token=args.token,
            username=args.username,
            password=args.password,
        )
        headers = {"Authorization": f"Bearer {token}"}

        results: list[QueryResult] = []
        for item in queries:
            query = str(item["query"]).strip()
            expected = [int(x) for x in item.get("expected_post_ids", [])]
            payload: dict[str, Any] = {
                "query": query,
                "limit": int(args.limit),
                "channel_ids": channel_ids,
            }
            if args.date_from:
                payload["date_from"] = args.date_from
            if args.date_to:
                payload["date_to"] = args.date_to

            notes = ""
            took_ms = 0
            total = 0
            top10: list[int] = []
            try:
                response = client.post(
                    f"{args.base_url.rstrip('/')}/api/keyword/search/posts",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if response.status_code >= 400:
                    notes = f"HTTP {response.status_code}: {response.text[:180]}"
                else:
                    data = response.json()
                    took_ms = int(data.get("took_ms") or 0)
                    total = int(data.get("total") or 0)
                    for row in (data.get("items") or [])[:10]:
                        post_id = row.get("post_id")
                        if isinstance(post_id, int):
                            top10.append(post_id)
            except Exception as exc:
                notes = f"EXC: {exc!r}"

            hits = len(set(top10).intersection(set(expected))) if expected else 0
            retrieved_k = max(1, len(top10))
            precision = (hits / float(retrieved_k)) if expected else 0.0
            results.append(
                QueryResult(
                    query=query,
                    filters=_build_filters_label(date_from=args.date_from, date_to=args.date_to, channel_ids=channel_ids),
                    took_ms=took_ms,
                    total=total,
                    top10_post_ids=top10,
                    expected_post_ids=expected,
                    hits_at_10=hits,
                    precision_at_10=precision,
                    notes=notes,
                )
            )

    report_text = _render_report(
        now_iso=now.isoformat(),
        base_url=args.base_url.rstrip("/"),
        channel_ids=channel_ids,
        date_from=args.date_from,
        date_to=args.date_to,
        results=results,
    )
    output_path.write_text(report_text, encoding="utf-8")
    print(f"[DONE] saved report: {output_path}")


if __name__ == "__main__":
    main()
