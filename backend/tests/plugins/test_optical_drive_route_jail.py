"""Die Routen des optical_drive-Plugins halten normale Nutzer in ihren Verzeichnissen.

Getestet wird ueber den echten Router; der Service laeuft im Dev-Modus.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.config import settings
from app.plugins.installed.optical_drive import OpticalDrivePlugin
from app.plugins.installed.optical_drive.service import OpticalDriveService

BASE = "/api/plugins/optical_drive"


class _User:
    def __init__(self, user_id: int, username: str, role: str):
        self.id = user_id
        self.username = username
        self.role = role


ALICE = _User(2, "alice", "user")
ADMIN = _User(1, "admin", "admin")


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    for name in ("alice", "bob"):
        (root / name).mkdir(parents=True)
    (root / "bob" / "secret.iso").write_bytes(b"x")
    (root / "bob" / "secret.wav").write_bytes(b"x")
    (root / "alice" / "mine.iso").write_bytes(b"x")
    (root / "alice" / "mine.wav").write_bytes(b"x")
    monkeypatch.setattr(settings, "nas_storage_path", str(root))
    return root


@pytest.fixture
def service(storage) -> OpticalDriveService:
    svc = OpticalDriveService()
    svc._is_dev_mode = True
    return svc


@pytest.fixture
def client_as(service, monkeypatch):
    plugin = OpticalDrivePlugin()
    monkeypatch.setattr(plugin, "service_with_current_config", lambda db: service)
    app = FastAPI()
    app.include_router(plugin.get_router(), prefix=BASE)

    def _client(user: _User) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    return _client


def _post_cases(storage):
    """(url, body) fuer jede Route mit einem Pfad in bobs Home."""
    bob = storage / "bob"
    return [
        ("/drives/sr0/read/iso", {"output_path": str(bob / "out.iso")}),
        ("/drives/sr0/read/audio", {"output_dir": str(bob / "rip")}),
        ("/drives/sr0/read/audio/1", {"track_number": 1, "output_path": str(bob / "t1.wav")}),
        ("/drives/sr0/extract", {"paths": ["/a"], "destination": str(bob / "ex")}),
        ("/iso/list", {"iso_path": str(bob / "secret.iso"), "path": "/"}),
        ("/iso/preview", {"iso_path": str(bob / "secret.iso"), "path": "/a"}),
        (
            "/iso/extract",
            {"iso_path": str(bob / "secret.iso"), "paths": ["/a"], "destination": str(bob / "ex")},
        ),
        (
            "/iso/extract",
            {
                "iso_path": str(storage / "alice" / "mine.iso"),
                "paths": ["/a"],
                "destination": str(bob / "ex"),
            },
        ),
        ("/drives/sr1/burn/iso", {"iso_path": str(bob / "secret.iso")}),
        (
            "/drives/sr1/burn/audio",
            {"wav_files": [str(storage / "alice" / "mine.wav"), str(bob / "secret.wav")]},
        ),
    ]


class TestForeignPathsAreRefused:
    @pytest.mark.parametrize("index", range(10))
    def test_normal_user_gets_403(self, client_as, storage, service, index):
        url, body = _post_cases(storage)[index]
        response = client_as(ALICE).post(f"{BASE}{url}", json=body)
        assert response.status_code == 403, response.text
        assert service.get_jobs(ALICE.id, True) == []
        assert not (storage / "bob" / "out.iso").exists()
        assert not (storage / "bob" / "rip").exists()
        assert not (storage / "bob" / "ex").exists()


class TestOwnPathsWork:
    def test_read_iso_into_own_home(self, client_as, storage):
        target = storage / "alice" / "out.iso"
        response = client_as(ALICE).post(
            f"{BASE}/drives/sr0/read/iso", json={"output_path": str(target)}
        )
        assert response.status_code == 200, response.text

    def test_burn_iso_from_own_home(self, client_as, storage):
        response = client_as(ALICE).post(
            f"{BASE}/drives/sr1/burn/iso",
            json={"iso_path": str(storage / "alice" / "mine.iso")},
        )
        assert response.status_code == 200, response.text


class TestAdminIsNotRestricted:
    def test_admin_reads_into_foreign_home(self, client_as, storage):
        target = storage / "bob" / "out.iso"
        response = client_as(ADMIN).post(
            f"{BASE}/drives/sr0/read/iso", json={"output_path": str(target)}
        )
        assert response.status_code == 200, response.text
