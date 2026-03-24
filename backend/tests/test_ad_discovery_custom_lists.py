"""Tests for custom lists service."""
import os
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.models.base import Base
from app.models.ad_discovery import AdDiscoveryCustomList, AdDiscoveryCustomListDomain
from app.services.pihole.ad_discovery.custom_lists import CustomListsService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(tmp_path):
    """CustomListsService with a temp directory for adlist files."""
    return CustomListsService(lists_dir=tmp_path)


@pytest.fixture
def mock_pihole():
    """Mock Pi-hole backend with async methods."""
    backend = MagicMock()
    backend.add_adlist = AsyncMock(return_value=None)
    backend.remove_adlist = AsyncMock(return_value=None)
    backend.update_gravity = AsyncMock(return_value=None)
    return backend


class TestCreateList:
    def test_create_list(self, db_session, service):
        """Create a list, verify name and description are stored in DB."""
        lst = service.create_list(db_session, name="My Blocklist", description="Test description")

        assert lst.id is not None
        assert lst.name == "My Blocklist"
        assert lst.description == "Test description"
        assert lst.domain_count == 0
        assert lst.deployed is False
        assert lst.adlist_url is None
        assert lst.created_at is not None
        assert lst.updated_at is not None

    def test_create_list_duplicate_name(self, db_session, service):
        """Creating two lists with the same name raises IntegrityError."""
        service.create_list(db_session, name="Duplicate")
        with pytest.raises(IntegrityError):
            service.create_list(db_session, name="Duplicate")


class TestAddDomains:
    def test_add_domains(self, db_session, service):
        """Adding domains updates domain_count correctly."""
        lst = service.create_list(db_session, name="Add Test")
        added = service.add_domains(db_session, lst.id, ["evil.com", "ads.example.com"])

        assert added == 2

        # Refresh from DB
        db_session.refresh(lst)
        assert lst.domain_count == 2

        # Verify rows exist
        domains = (
            db_session.query(AdDiscoveryCustomListDomain)
            .filter(AdDiscoveryCustomListDomain.list_id == lst.id)
            .all()
        )
        domain_values = {d.domain for d in domains}
        assert "evil.com" in domain_values
        assert "ads.example.com" in domain_values

    def test_add_domains_duplicate(self, db_session, service):
        """Adding the same domain twice skips the duplicate gracefully."""
        lst = service.create_list(db_session, name="Dup Domain Test")
        service.add_domains(db_session, lst.id, ["evil.com"])
        added = service.add_domains(db_session, lst.id, ["evil.com", "ads.example.com"])

        assert added == 1  # Only the new domain is added

        db_session.refresh(lst)
        assert lst.domain_count == 2

    def test_add_domains_normalizes_case(self, db_session, service):
        """Domains are lowercased before storage."""
        lst = service.create_list(db_session, name="Case Test")
        service.add_domains(db_session, lst.id, ["EVIL.COM"])
        service.add_domains(db_session, lst.id, ["evil.com"])  # Same after lowercasing — duplicate

        db_session.refresh(lst)
        assert lst.domain_count == 1

    def test_add_domains_list_not_found(self, db_session, service):
        """Adding domains to a nonexistent list raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            service.add_domains(db_session, 9999, ["evil.com"])


class TestRemoveDomain:
    def test_remove_domain(self, db_session, service):
        """Removing a domain decrements domain_count."""
        lst = service.create_list(db_session, name="Remove Test")
        service.add_domains(db_session, lst.id, ["evil.com", "ads.example.com"])

        removed = service.remove_domain(db_session, lst.id, "evil.com")
        assert removed is True

        db_session.refresh(lst)
        assert lst.domain_count == 1

        domains = (
            db_session.query(AdDiscoveryCustomListDomain)
            .filter(AdDiscoveryCustomListDomain.list_id == lst.id)
            .all()
        )
        assert len(domains) == 1
        assert domains[0].domain == "ads.example.com"

    def test_remove_domain_not_found(self, db_session, service):
        """Removing a nonexistent domain returns False."""
        lst = service.create_list(db_session, name="Remove Not Found")
        removed = service.remove_domain(db_session, lst.id, "doesnotexist.com")
        assert removed is False


class TestGenerateAdlistContent:
    def test_generate_adlist_content(self, db_session, service):
        """Generated content has a header comment and sorted domains."""
        lst = service.create_list(db_session, name="Export List", description="Test")
        service.add_domains(db_session, lst.id, ["zebra.com", "apple.com", "mango.net"])

        content = service.generate_adlist_content(db_session, lst.id)

        assert "# BaluHost Custom Blocklist: Export List" in content
        assert "# Generated:" in content
        assert "# Domains: 3" in content

        # Domains must be sorted
        lines = [l for l in content.splitlines() if l and not l.startswith("#")]
        assert lines == ["apple.com", "mango.net", "zebra.com"]

    def test_generate_adlist_content_list_not_found(self, db_session, service):
        """generate_adlist_content raises ValueError for unknown list ID."""
        with pytest.raises(ValueError, match="not found"):
            service.generate_adlist_content(db_session, 9999)

    def test_generate_adlist_content_ends_with_newline(self, db_session, service):
        """Generated content ends with a trailing newline."""
        lst = service.create_list(db_session, name="Newline Test")
        service.add_domains(db_session, lst.id, ["evil.com"])
        content = service.generate_adlist_content(db_session, lst.id)
        assert content.endswith("\n")


class TestExportList:
    def test_export_list(self, db_session, service):
        """Export returns bytes containing the header and domains."""
        lst = service.create_list(db_session, name="Bytes Export")
        service.add_domains(db_session, lst.id, ["ads.net", "tracker.io"])

        data = service.export_list(db_session, lst.id)

        assert isinstance(data, bytes)
        text = data.decode("utf-8")
        assert "# BaluHost Custom Blocklist: Bytes Export" in text
        assert "ads.net" in text
        assert "tracker.io" in text


class TestDeleteList:
    def test_delete_list(self, db_session, service):
        """Deleting a list cascades to all its domains."""
        lst = service.create_list(db_session, name="Delete Me")
        service.add_domains(db_session, lst.id, ["evil.com", "tracker.net"])
        list_id = lst.id

        result = service.delete_list(db_session, list_id)
        assert result is True

        # List is gone
        assert db_session.query(AdDiscoveryCustomList).filter(
            AdDiscoveryCustomList.id == list_id
        ).first() is None

        # Domains are gone (CASCADE)
        remaining = db_session.query(AdDiscoveryCustomListDomain).filter(
            AdDiscoveryCustomListDomain.list_id == list_id
        ).all()
        assert remaining == []

    def test_delete_list_not_found(self, db_session, service):
        """Deleting a nonexistent list returns False."""
        result = service.delete_list(db_session, 9999)
        assert result is False


class TestGetLists:
    def test_get_list(self, db_session, service):
        """get_list returns the correct list by ID."""
        created = service.create_list(db_session, name="Fetch Me")
        fetched = service.get_list(db_session, created.id)
        assert fetched is not None
        assert fetched.name == "Fetch Me"

    def test_get_list_not_found(self, db_session, service):
        """get_list returns None for unknown ID."""
        assert service.get_list(db_session, 9999) is None

    def test_get_all_lists(self, db_session, service):
        """get_all_lists returns all created lists."""
        service.create_list(db_session, name="List A")
        service.create_list(db_session, name="List B")
        all_lists = service.get_all_lists(db_session)
        names = {lst.name for lst in all_lists}
        assert "List A" in names
        assert "List B" in names

    def test_update_list(self, db_session, service):
        """update_list changes name and description."""
        lst = service.create_list(db_session, name="Old Name", description="Old desc")
        updated = service.update_list(db_session, lst.id, name="New Name", description="New desc")
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.description == "New desc"

    def test_update_list_not_found(self, db_session, service):
        """update_list returns None for unknown ID."""
        result = service.update_list(db_session, 9999, name="X")
        assert result is None


def _run(coro):
    """Run a coroutine in a fresh event loop (Python 3.14 compatible)."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestDeployToPihole:
    def test_deploy_to_pihole(self, db_session, service, mock_pihole):
        """deploy_to_pihole calls add_adlist + update_gravity and marks deployed."""
        lst = service.create_list(db_session, name="Deploy Test")
        service.add_domains(db_session, lst.id, ["evil.com"])

        url = _run(
            service.deploy_to_pihole(
                db_session,
                lst.id,
                base_url="http://localhost:3001",
                pihole_backend=mock_pihole,
            )
        )

        mock_pihole.add_adlist.assert_called_once()
        mock_pihole.update_gravity.assert_called_once()

        db_session.refresh(lst)
        assert lst.deployed is True
        assert lst.adlist_url == url

    def test_undeploy_from_pihole(self, db_session, service, mock_pihole):
        """undeploy_from_pihole calls remove_adlist + update_gravity and clears deployed."""
        lst = service.create_list(db_session, name="Undeploy Test")
        service.add_domains(db_session, lst.id, ["evil.com"])

        # Deploy first
        _run(
            service.deploy_to_pihole(
                db_session,
                lst.id,
                base_url="http://localhost:3001",
                pihole_backend=mock_pihole,
            )
        )

        # Then undeploy
        _run(
            service.undeploy_from_pihole(db_session, lst.id, pihole_backend=mock_pihole)
        )

        mock_pihole.remove_adlist.assert_called_once()

        db_session.refresh(lst)
        assert lst.deployed is False
        assert lst.adlist_url is None
