from pathlib import Path
import sys
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.processes.build_processes import _build_update_components


def test_build_update_components_applies_transitivity() -> None:
    links = [
        SimpleNamespace(
            src_post_id=101,
            dst_post_id=102,
            score=0.8,
            evidence_json={"edge": "a-b"},
            model_version="test",
            pipeline_version="test",
        ),
        SimpleNamespace(
            src_post_id=201,
            dst_post_id=202,
            score=0.9,
            evidence_json={"edge": "b-c"},
            model_version="test",
            pipeline_version="test",
        ),
    ]
    post_to_event_ids = {
        101: {1},
        102: {2},
        201: {2},
        202: {3},
    }

    components, payload = _build_update_components(
        event_ids={1, 2, 3},
        post_to_event_ids=post_to_event_ids,
        links=links,
    )

    assert sorted(sorted(component) for component in components) == [[1, 2, 3]]
    assert set(payload) == {1, 2, 3}


def test_build_update_components_ignores_edges_without_cross_event_mapping() -> None:
    links = [
        SimpleNamespace(
            src_post_id=101,
            dst_post_id=102,
            score=0.8,
            evidence_json={"edge": "same-event"},
            model_version="test",
            pipeline_version="test",
        ),
    ]
    post_to_event_ids = {
        101: {1},
        102: {1},
    }

    components, payload = _build_update_components(
        event_ids={1},
        post_to_event_ids=post_to_event_ids,
        links=links,
    )

    assert components == []
    assert payload == {}
