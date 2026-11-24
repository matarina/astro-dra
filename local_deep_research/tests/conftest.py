import pytest


@pytest.fixture
def native_review_only(monkeypatch):
    """Isolate native review tests whose model replies only implement that protocol."""
    from research_verify import task_evidence

    monkeypatch.setattr(task_evidence, "task_coverage", lambda *args, **kwargs: {})
