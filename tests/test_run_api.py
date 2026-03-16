from __future__ import annotations

from scripts import run_api


def test_run_api_main_invokes_uvicorn_with_canonical_app(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        run_api,
        "uvicorn",
        type(
            "_FakeUvicorn",
            (),
            {"run": staticmethod(lambda app, **kwargs: calls.append({"app": app, **kwargs}))},
        )(),
    )
    monkeypatch.setattr(
        run_api.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("_Args", (), {"host": "0.0.0.0", "port": 9000, "reload": True})(),
    )

    run_api.main()

    assert calls == [
        {
            "app": "api.main:app",
            "host": "0.0.0.0",
            "port": 9000,
            "reload": True,
        }
    ]
