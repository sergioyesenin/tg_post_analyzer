from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import httpx


DEFAULT_CASES: list[dict[str, Any]] = [
    {
        "name": "weather_cross_channel",
        "post_ids": [669, 645, 531, 495, 377, 289, 246, 382, 297, 387],
        "exclude_post_ids": [],
        "graph_mode": "transient",
        "include_neighbors": True,
        "neighbor_depth": 1,
        "neighbor_limit": 400,
        "allowed_link_types": [],
        "min_shared_lemmas": 2,
        "max_time_distance_hours": 96,
        "min_text_similarity": 0.2,
    },
    {
        "name": "minsk_mir_cluster",
        "post_ids": [90, 481, 135, 204, 91],
        "exclude_post_ids": [],
        "graph_mode": "transient",
        "include_neighbors": True,
        "neighbor_depth": 1,
        "neighbor_limit": 400,
        "allowed_link_types": [],
        "min_shared_lemmas": 2,
        "max_time_distance_hours": 96,
        "min_text_similarity": 0.2,
    },
    {
        "name": "fires_cluster",
        "post_ids": [756, 703, 664, 637, 509, 476, 427, 288, 149, 54],
        "exclude_post_ids": [],
        "graph_mode": "transient",
        "include_neighbors": True,
        "neighbor_depth": 1,
        "neighbor_limit": 400,
        "allowed_link_types": [],
        "min_shared_lemmas": 2,
        "max_time_distance_hours": 96,
        "min_text_similarity": 0.2,
    },
]


@dataclass
class CaseResult:
    name: str
    graph_mode: str
    post_ids: list[int]
    exclude_post_ids: list[int]
    include_neighbors: bool
    neighbor_depth: int
    nodes: int
    edges: int
    neighbor_nodes: int
    edge_sources: dict[str, int]
    top_edge_types: dict[str, int]
    status_code: int
    error: str = ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run POST /api/keyword/graph/build tests and save report to docs/*.txt",
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", help="Login username (local auth)")
    parser.add_argument("--password", help="Login password (local auth)")
    parser.add_argument("--token", help="Bearer token. If set, login step is skipped.")
    parser.add_argument(
        "--cases-file",
        help="Optional JSON file with graph-build cases. Format: [{\"name\":\"...\",\"post_ids\":[...]}]",
    )
    parser.add_argument(
        "--output",
        help="Output path. Default: docs/keyword_graph_build_test_results_<timestamp>.txt",
    )
    return parser.parse_args()


def _auth_token(
    client: httpx.Client,
    *,
    base_url: str,
    token: str | None,
    username: str | None,
    password: str | None,
) -> str:
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


def _load_cases(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return DEFAULT_CASES
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("cases-file must contain JSON array")
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        post_ids = item.get("post_ids", item.get("seed_post_ids", []))
        if not isinstance(post_ids, list) or not post_ids:
            continue
        case = {
            "name": str(item.get("name") or f"case_{idx}"),
            "post_ids": [int(x) for x in post_ids],
            "exclude_post_ids": [int(x) for x in item.get("exclude_post_ids", [])],
            "graph_mode": str(item.get("graph_mode", "transient")),
            "include_neighbors": bool(item.get("include_neighbors", True)),
            "neighbor_depth": int(item.get("neighbor_depth", 1)),
            "neighbor_limit": int(item.get("neighbor_limit", 400)),
            "allowed_link_types": list(item.get("allowed_link_types", [])),
            "min_shared_lemmas": int(item.get("min_shared_lemmas", 2)),
            "max_time_distance_hours": int(item.get("max_time_distance_hours", 96)),
            "min_text_similarity": float(item.get("min_text_similarity", 0.2)),
        }
        out.append(case)
    if not out:
        raise ValueError("cases-file does not contain valid cases")
    return out


def _count_values(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in items:
        value = str(row.get(key, ""))
        if not value:
            continue
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _render_report(
    *,
    now_iso: str,
    base_url: str,
    cases_total: int,
    results: list[CaseResult],
) -> str:
    ok_results = [r for r in results if r.status_code < 400]
    err_results = [r for r in results if r.status_code >= 400]

    avg_nodes = round(mean([r.nodes for r in ok_results]), 2) if ok_results else 0
    avg_edges = round(mean([r.edges for r in ok_results]), 2) if ok_results else 0
    ok_mark = sum(1 for r in ok_results if r.edges > 0)
    missing_links_mark = sum(1 for r in ok_results if r.edges == 0)

    lines: list[str] = []
    lines.append("# Keyword Graph Build API Test Results")
    lines.append("")
    lines.append(f"- Generated at (UTC): {now_iso}")
    lines.append(f"- Base URL: {base_url}")
    lines.append("")
    lines.append("## 3.1 Summary")
    lines.append(f"- Cases tested: {cases_total}")
    lines.append(f"- Avg nodes: {avg_nodes}")
    lines.append(f"- Avg edges: {avg_edges}")
    lines.append(f"- Cases marked `ok` (edges>0): {ok_mark}")
    lines.append(f"- Cases marked `missing_links` (edges=0): {missing_links_mark}")
    lines.append(f"- Errors (4xx/5xx): {len(err_results)}")
    lines.append("")
    lines.append("## 3.2 Per-case Results")
    lines.append(
        "| # | name | seed_post_ids | exclude_post_ids | graph_mode | include_neighbors/depth | nodes | edges | edge_sources | top_edge_types | manual_mark | notes |"
    )
    lines.append(
        "|---|------|---------------|------------------|------------|--------------------------|-------|-------|--------------|----------------|------------|-------|"
    )
    for idx, row in enumerate(results, start=1):
        if row.status_code >= 400:
            manual_mark = "error"
            notes = f"HTTP {row.status_code}: {row.error}"
        else:
            manual_mark = "ok" if row.edges > 0 else "missing_links"
            notes = ""
        lines.append(
            f"| {idx} | {row.name} | {row.post_ids} | {row.exclude_post_ids} | {row.graph_mode} | "
            f"{row.include_neighbors}/{row.neighbor_depth} | {row.nodes} | {row.edges} | "
            f"{row.edge_sources} | {row.top_edge_types} | {manual_mark} | {notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")
    cases = _load_cases(args.cases_file)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d%H%M%S")
    output_path = Path(args.output) if args.output else Path("docs") / f"keyword_graph_build_test_results_{timestamp}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[CaseResult] = []
    with httpx.Client() as client:
        token = _auth_token(
            client,
            base_url=base_url,
            token=args.token,
            username=args.username,
            password=args.password,
        )
        headers = {"Authorization": f"Bearer {token}"}

        for case in cases:
            payload = {
                "post_ids": case["post_ids"],
                "exclude_post_ids": case["exclude_post_ids"],
                "graph_mode": case["graph_mode"],
                "include_neighbors": case["include_neighbors"],
                "neighbor_depth": case["neighbor_depth"],
                "neighbor_limit": case["neighbor_limit"],
                "allowed_link_types": case["allowed_link_types"],
                "min_shared_lemmas": case["min_shared_lemmas"],
                "max_time_distance_hours": case["max_time_distance_hours"],
                "min_text_similarity": case["min_text_similarity"],
            }
            status_code = 0
            error = ""
            nodes_count = 0
            edges_count = 0
            neighbor_nodes = 0
            edge_sources: dict[str, int] = {}
            top_edge_types: dict[str, int] = {}

            try:
                resp = client.post(
                    f"{base_url}/api/keyword/graph/build",
                    headers=headers,
                    json=payload,
                    timeout=180,
                )
                status_code = resp.status_code
                if status_code >= 400:
                    error = resp.text[:240]
                else:
                    data = resp.json()
                    nodes = data.get("nodes") or []
                    edges = data.get("edges") or []
                    if isinstance(nodes, list):
                        nodes_count = len(nodes)
                        neighbor_nodes = sum(1 for n in nodes if isinstance(n, dict) and n.get("included_by") == "neighbor")
                    if isinstance(edges, list):
                        edges_count = len(edges)
                        edge_sources = _count_values([e for e in edges if isinstance(e, dict)], "edge_source")
                        top_edge_types = _count_values([e for e in edges if isinstance(e, dict)], "link_type")
            except Exception as exc:
                status_code = 500
                error = repr(exc)

            results.append(
                CaseResult(
                    name=str(case["name"]),
                    graph_mode=str(case["graph_mode"]),
                    post_ids=list(case["post_ids"]),
                    exclude_post_ids=list(case["exclude_post_ids"]),
                    include_neighbors=bool(case["include_neighbors"]),
                    neighbor_depth=int(case["neighbor_depth"]),
                    nodes=nodes_count,
                    edges=edges_count,
                    neighbor_nodes=neighbor_nodes,
                    edge_sources=edge_sources,
                    top_edge_types=top_edge_types,
                    status_code=status_code,
                    error=error,
                )
            )

    report = _render_report(
        now_iso=now.isoformat(),
        base_url=base_url,
        cases_total=len(cases),
        results=results,
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"[DONE] saved report: {output_path}")


if __name__ == "__main__":
    main()
