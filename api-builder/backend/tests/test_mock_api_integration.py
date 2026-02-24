from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from mock_api.app.main import app


@pytest.mark.integration
def test_users_pagination() -> None:
    client = TestClient(app)
    response = client.get("/users", params={"page": 2, "page_size": 7})
    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 7
    assert len(payload["data"]) == 7
    assert payload["total"] >= 7


@pytest.mark.integration
def test_branch_logic_true_and_false_paths() -> None:
    client = TestClient(app)
    approved = client.post("/logic/branch", json={"amount": 80, "retries": 0})
    review = client.post("/logic/branch", json={"amount": 500, "retries": 0})

    assert approved.status_code == 200
    assert review.status_code == 200
    assert approved.json()["approved"] is True
    assert review.json()["approved"] is False


@pytest.mark.integration
def test_flaky_endpoint_transitions_to_success() -> None:
    client = TestClient(app)
    key = "integration-test"
    first = client.post("/resilience/flaky", params={"key": key, "fail_until": 2})
    second = client.post("/resilience/flaky", params={"key": key, "fail_until": 2})
    third = client.post("/resilience/flaky", params={"key": key, "fail_until": 2})

    assert first.status_code == 503
    assert second.status_code == 503
    assert third.status_code == 200
    assert third.json()["status"] == "ok_after_retries"
