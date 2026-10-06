"""Job-Eigentuemer im optical_drive-Plugin (#633).

Jobs liegen im Service-Singleton; ohne Eigentuemer sah und brach jeder User die
Jobs aller anderen ab. Getestet wird ueber den echten Router.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.plugins.installed.optical_drive import OpticalDrivePlugin
from app.plugins.installed.optical_drive.models import JobStatus, JobType
from app.plugins.installed.optical_drive.service import OpticalDriveService

BASE = "/api/plugins/optical_drive"


class _User:
    def __init__(self, user_id: int, role: str):
        self.id = user_id
        self.username = f"u{user_id}"
        self.role = role


ALICE = _User(2, "user")
BOB = _User(3, "user")
ADMIN = _User(1, "admin")


@pytest.fixture
def service() -> OpticalDriveService:
    svc = OpticalDriveService()
    svc._is_dev_mode = True
    return svc


@pytest.fixture
def as_user(service, monkeypatch):
    """Liefert eine Funktion, die einen Client fuer den gewaehlten User baut."""
    plugin = OpticalDrivePlugin()
    monkeypatch.setattr(plugin, "service_with_current_config", lambda db: service)
    app = FastAPI()
    app.include_router(plugin.get_router(), prefix=BASE)

    def _client(user: _User) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    return _client


@pytest.fixture
def alice_job(service):
    job = service._create_job(
        "/dev/sr0", JobType.READ_ISO, output_path="/storage/alice/disc.iso",
        owner_id=ALICE.id,
    )
    service._update_job(job.id, status=JobStatus.RUNNING)
    return job


class TestListJobs:
    def test_owner_sees_own_job(self, as_user, alice_job):
        body = as_user(ALICE).get(f"{BASE}/jobs").json()
        assert [j["id"] for j in body["jobs"]] == [alice_job.id]
        assert body["total"] == 1

    def test_other_user_does_not_see_job(self, as_user, alice_job):
        body = as_user(BOB).get(f"{BASE}/jobs").json()
        assert body["jobs"] == []
        assert body["total"] == 0

    def test_admin_sees_all_jobs(self, as_user, alice_job):
        body = as_user(ADMIN).get(f"{BASE}/jobs").json()
        assert [j["id"] for j in body["jobs"]] == [alice_job.id]

    def test_job_without_owner_is_hidden_from_users(self, as_user, service):
        service._create_job("/dev/sr0", JobType.BLANK)
        assert as_user(ALICE).get(f"{BASE}/jobs").json()["jobs"] == []
        assert len(as_user(ADMIN).get(f"{BASE}/jobs").json()["jobs"]) == 1

    def test_owner_id_is_not_exposed(self, as_user, alice_job):
        job = as_user(ALICE).get(f"{BASE}/jobs").json()["jobs"][0]
        assert "owner_id" not in job


class TestGetJob:
    def test_owner_gets_job(self, as_user, alice_job):
        resp = as_user(ALICE).get(f"{BASE}/jobs/{alice_job.id}")
        assert resp.status_code == 200

    def test_other_user_gets_404(self, as_user, alice_job):
        resp = as_user(BOB).get(f"{BASE}/jobs/{alice_job.id}")
        assert resp.status_code == 404

    def test_foreign_and_unknown_job_look_identical(self, as_user, alice_job):
        foreign = as_user(BOB).get(f"{BASE}/jobs/{alice_job.id}")
        unknown = as_user(BOB).get(f"{BASE}/jobs/{alice_job.id}-x")
        assert foreign.json()["detail"].replace(alice_job.id, "X") == (
            unknown.json()["detail"].replace(f"{alice_job.id}-x", "X")
        )

    def test_admin_gets_foreign_job(self, as_user, alice_job):
        resp = as_user(ADMIN).get(f"{BASE}/jobs/{alice_job.id}")
        assert resp.status_code == 200


class TestCancelJob:
    def test_other_user_cannot_cancel(self, as_user, service, alice_job):
        resp = as_user(BOB).post(f"{BASE}/jobs/{alice_job.id}/cancel")
        assert resp.status_code == 400
        assert service._jobs[alice_job.id].status == JobStatus.RUNNING

    def test_owner_can_cancel(self, as_user, service, alice_job):
        resp = as_user(ALICE).post(f"{BASE}/jobs/{alice_job.id}/cancel")
        assert resp.status_code == 200
        assert service._jobs[alice_job.id].status == JobStatus.CANCELLED

    def test_admin_can_cancel_foreign_job(self, as_user, service, alice_job):
        resp = as_user(ADMIN).post(f"{BASE}/jobs/{alice_job.id}/cancel")
        assert resp.status_code == 200
        assert service._jobs[alice_job.id].status == JobStatus.CANCELLED


class TestJobCreationRecordsOwner:
    def test_job_started_through_route_belongs_to_caller(self, as_user):
        resp = as_user(ALICE).post(f"{BASE}/drives/sr1/blank", json={"mode": "fast"})
        assert resp.status_code == 200
        job_id = resp.json()["id"]

        assert as_user(ALICE).get(f"{BASE}/jobs/{job_id}").status_code == 200
        assert as_user(BOB).get(f"{BASE}/jobs/{job_id}").status_code == 404
