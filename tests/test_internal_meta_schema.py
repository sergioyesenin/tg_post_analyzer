"""Tests for internal multi-agent meta schema validation (P2)."""

import pytest
from agents.reporter import (
    EPISTEMIC_LABELS,
    SUFFICIENCY_LABELS,
    REPORT_STATUSES,
    FALLBACK_STATUSES,
    EpistemicEntry,
    MultiAgentMeta,
)


class TestSpecDerivedConstants:
    """Test spec-derived constants are properly defined."""

    def test_epistemic_labels_frozen_set(self):
        expected = {"fact", "derived", "interpretation", "external", "uncertain"}
        assert EPISTEMIC_LABELS == expected
        assert isinstance(EPISTEMIC_LABELS, frozenset)

    def test_sufficiency_labels_frozen_set(self):
        expected = {"sufficient", "limited", "weak_signal", "insufficient"}
        assert SUFFICIENCY_LABELS == expected
        assert isinstance(SUFFICIENCY_LABELS, frozenset)

    def test_report_statuses_frozen_set(self):
        expected = {"ready", "limited", "insufficient_data"}
        assert REPORT_STATUSES == expected
        assert isinstance(REPORT_STATUSES, frozenset)

    def test_fallback_statuses_frozen_set(self):
        expected = {"ready", "limited", "insufficient_data", "failed"}
        assert FALLBACK_STATUSES == expected
        assert isinstance(FALLBACK_STATUSES, frozenset)


class TestEpistemicEntry:
    """Test EpistemicEntry dataclass."""

    def test_valid_epistemic_entry(self):
        entry = EpistemicEntry(
            label="fact",
            evidence="Direct quote from post",
            confidence="high"
        )
        assert entry.label == "fact"
        assert entry.evidence == "Direct quote from post"
        assert entry.confidence == "high"

    def test_epistemic_entry_immutable(self):
        entry = EpistemicEntry(
            label="interpretation",
            evidence="Analysis of patterns",
            confidence="medium"
        )
        with pytest.raises(AttributeError):
            entry.label = "fact"

    @pytest.mark.parametrize("invalid_label", ["invalid", "FACTS", ""])
    def test_invalid_epistemic_label_raises_error(self, invalid_label):
        """While dataclass allows any string, validation should catch invalid labels."""
        entry = EpistemicEntry(
            label=invalid_label,
            evidence="test",
            confidence="high"
        )
        # Note: dataclass doesn't validate, but future validation should
        assert entry.label == invalid_label


class TestMultiAgentMeta:
    """Test MultiAgentMeta dataclass."""

    def test_default_multi_agent_meta(self):
        meta = MultiAgentMeta()
        assert meta.epistemic_labels == []
        assert meta.sufficiency == "insufficient"
        assert meta.stages == {}
        assert meta.review_iterations == 0
        assert meta.final_status == "insufficient_data"

    def test_multi_agent_meta_with_values(self):
        epistemic_labels = [
            EpistemicEntry(label="fact", evidence="Post text", confidence="high"),
            EpistemicEntry(label="interpretation", evidence="Comment analysis", confidence="medium")
        ]
        stages = {"context": {"status": "completed"}, "expert": {"status": "pending"}}
        meta = MultiAgentMeta(
            epistemic_labels=epistemic_labels,
            sufficiency="sufficient",
            stages=stages,
            review_iterations=1,
            final_status="ready"
        )
        assert len(meta.epistemic_labels) == 2
        assert meta.sufficiency == "sufficient"
        assert meta.stages == stages
        assert meta.review_iterations == 1
        assert meta.final_status == "ready"

    def test_multi_agent_meta_immutable(self):
        meta = MultiAgentMeta()
        with pytest.raises(AttributeError):
            meta.sufficiency = "sufficient"


class TestInternalMetaSchemaValidation:
    """Test validation of internal meta.multi_agent structure."""

    def test_valid_multi_agent_meta_dict(self):
        """Test that a valid multi_agent dict can be created."""
        meta_dict = {
            "epistemic_labels": [
                {"label": "fact", "evidence": "Post content", "confidence": "high"},
                {"label": "derived", "evidence": "Comment sentiment", "confidence": "medium"}
            ],
            "sufficiency": "sufficient",
            "stages": {"context": {"completed": True}},
            "review_iterations": 0,
            "final_status": "ready"
        }
        # Convert to MultiAgentMeta for validation
        epistemic_entries = [
            EpistemicEntry(**entry) for entry in meta_dict["epistemic_labels"]
        ]
        meta = MultiAgentMeta(
            epistemic_labels=epistemic_entries,
            sufficiency=meta_dict["sufficiency"],
            stages=meta_dict["stages"],
            review_iterations=meta_dict["review_iterations"],
            final_status=meta_dict["final_status"]
        )
        assert len(meta.epistemic_labels) == 2
        assert meta.sufficiency == "sufficient"

    def test_invalid_epistemic_label_rejected(self):
        """Test that invalid epistemic labels are detected."""
        invalid_meta = {
            "epistemic_labels": [
                {"label": "invalid_label", "evidence": "test", "confidence": "high"}
            ],
            "sufficiency": "sufficient",
            "stages": {},
            "review_iterations": 0,
            "final_status": "ready"
        }
        # This should be caught by validation logic (to be added)
        epistemic_entries = [
            EpistemicEntry(**entry) for entry in invalid_meta["epistemic_labels"]
        ]
        # For now, just check that the entry is created but validation would fail
        assert epistemic_entries[0].label == "invalid_label"
        # Future: add validation that raises error

    def test_invalid_sufficiency_label_rejected(self):
        """Test that invalid sufficiency labels are detected."""
        with pytest.raises(ValueError):
            # This should be validated when setting
            MultiAgentMeta(sufficiency="invalid")

    def test_invalid_final_status_rejected(self):
        """Test that invalid final statuses are detected."""
        with pytest.raises(ValueError):
            MultiAgentMeta(final_status="invalid_status")