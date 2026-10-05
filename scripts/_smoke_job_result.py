"""Одноразовый smoke-тест для Шага 1.2. Удалить после проверки."""
from __future__ import annotations

from types import SimpleNamespace

from services.jobs import JOB_RESULT_SCHEMAS, set_job_result, get_job_result, JobType, JOB_RESULT_KEY


def _job(job_type: str):
    return SimpleNamespace(type=job_type, payload_json={})


def test_happy_path_post_report():
    job = _job(JobType.BUILD_POST_REPORT)
    set_job_result(job, {"status": "ready", "post_id": 42, "report_id": 7})
    stored = get_job_result(job)
    assert stored["status"] == "ready"
    assert stored["post_id"] == 42
    assert stored["report_id"] == 7
    print("OK post_report")


def test_happy_path_comment_refresh():
    job = _job(JobType.REFRESH_COMMENTS)
    set_job_result(job, {"status": "ok", "comments_saved": 3})
    assert get_job_result(job)["comments_saved"] == 3
    print("OK comment_refresh")


def test_deferred_event_report():
    job = _job(JobType.BUILD_EVENT_REPORT)
    set_job_result(job, {
        "status": "deferred",
        "reason": "waiting_post_reports",
        "dependencies": [{"job_type": "build_post_report", "post_id": 77}],
    })
    stored = get_job_result(job)
    assert stored["reason"] == "waiting_post_reports"
    assert len(stored["dependencies"]) == 1
    print("OK deferred_event_report")


def test_missing_status_raises():
    job = _job(JobType.BUILD_POST_REPORT)
    try:
        set_job_result(job, {"post_id": 42})
    except Exception as exc:
        print(f"OK missing status raised: {type(exc).__name__}")
        return
    raise AssertionError("Missing status should have raised ValidationError")


def test_extra_fields_allowed():
    job = _job(JobType.BUILD_POST_REPORT)
    set_job_result(job, {"status": "ready", "post_id": 1, "custom_debug": {"x": 1}})
    assert get_job_result(job)["custom_debug"] == {"x": 1}
    print("OK extra fields preserved")


def test_unknown_job_type_no_validation():
    job = _job("something_new")
    set_job_result(job, {"anything": "goes", "status": "ok"})
    assert get_job_result(job)["anything"] == "goes"
    print("OK unknown type passthrough")


def test_schemas_registry_covers_known_types():
    known = [
        JobType.ADD_CHANNEL, JobType.BUILD_POST_LINKS, JobType.BUILD_POST_REPORT,
        JobType.BUILD_POST_REPORT_BATCH, JobType.BUILD_EVENT_REPORT,
        JobType.BUILD_PROCESS_REPORT, JobType.COLLECT_COMMENTS,
        JobType.REFRESH_COMMENTS, JobType.REBUILD_EVENTS,
        JobType.REBUILD_PROCESSES, JobType.ARCHIVE_RETENTION,
        JobType.JOBS_RETENTION,
    ]
    missing = [t for t in known if t not in JOB_RESULT_SCHEMAS]
    assert not missing, f"Missing schemas for: {missing}"
    print(f"OK registry covers {len(known)} types")


if __name__ == "__main__":
    test_happy_path_post_report()
    test_happy_path_comment_refresh()
    test_deferred_event_report()
    test_missing_status_raises()
    test_extra_fields_allowed()
    test_unknown_job_type_no_validation()
    test_schemas_registry_covers_known_types()
    print("\nAll smoke checks passed.")