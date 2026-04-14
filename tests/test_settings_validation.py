from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.settings_validation import validate_setting_payload


def test_validate_comments_settings_accepts_long_comment_threshold():
    payload = validate_setting_payload("comments", {"long_comment_threshold": 100})

    assert payload["long_comment_threshold"] == 100


def test_validate_comments_settings_rejects_long_comment_threshold_below_min():
    with pytest.raises(ValidationError):
        validate_setting_payload("comments", {"long_comment_threshold": 0})


def test_validate_comments_settings_rejects_long_comment_threshold_above_max():
    with pytest.raises(ValidationError):
        validate_setting_payload("comments", {"long_comment_threshold": 10001})
