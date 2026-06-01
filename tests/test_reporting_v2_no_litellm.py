from __future__ import annotations

import ast
from pathlib import Path


def _reporting_v2_files() -> list[Path]:
    root = Path("services/reporting_v2")
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def test_reporting_v2_has_no_litellm_imports() -> None:
    offenders: list[str] = []

    for path in _reporting_v2_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "litellm" or alias.name.startswith("litellm."):
                        offenders.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "litellm" or module.startswith("litellm."):
                    offenders.append(f"{path}: from {module} import ...")

    assert offenders == [], "Found forbidden litellm imports:\n" + "\n".join(offenders)
