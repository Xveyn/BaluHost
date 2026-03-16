"""Tests for services/rate_limit_config.py — RateLimitConfig CRUD."""

import pytest
from sqlalchemy.orm import Session

from app.models.rate_limit_config import RateLimitConfig
from app.schemas.rate_limit_config import RateLimitConfigCreate, RateLimitConfigUpdate
from app.services.rate_limit_config import RateLimitConfigService


def _create_config(
    db: Session,
    endpoint_type: str = "auth_login",
    limit_string: str = "5/minute",
    description: str = "Login limit",
    enabled: bool = True,
    user_id: int = 1,
) -> RateLimitConfig:
    schema = RateLimitConfigCreate(
        endpoint_type=endpoint_type,
        limit_string=limit_string,
        description=description,
        enabled=enabled,
    )
    return RateLimitConfigService.create(db, schema, user_id)


class TestGetAll:
    def test_empty_initially(self, db_session: Session):
        assert list(RateLimitConfigService.get_all(db_session)) == []

    def test_returns_all_configs(self, db_session: Session):
        _create_config(db_session, endpoint_type="a", limit_string="1/minute")
        _create_config(db_session, endpoint_type="b", limit_string="2/minute")
        result = RateLimitConfigService.get_all(db_session)
        assert len(list(result)) == 2


class TestGetByEndpointType:
    def test_returns_none_when_not_found(self, db_session: Session):
        assert RateLimitConfigService.get_by_endpoint_type(db_session, "nope") is None

    def test_returns_matching_config(self, db_session: Session):
        _create_config(db_session, endpoint_type="file_upload", limit_string="20/minute")
        result = RateLimitConfigService.get_by_endpoint_type(db_session, "file_upload")
        assert result is not None
        assert result.limit_string == "20/minute"


class TestGetEnabledConfigs:
    def test_returns_only_enabled(self, db_session: Session):
        _create_config(db_session, endpoint_type="a", limit_string="1/minute", enabled=True)
        _create_config(db_session, endpoint_type="b", limit_string="2/minute", enabled=False)

        result = RateLimitConfigService.get_enabled_configs(db_session)
        assert result == {"a": "1/minute"}

    def test_empty_when_none_enabled(self, db_session: Session):
        _create_config(db_session, endpoint_type="x", limit_string="1/minute", enabled=False)
        assert RateLimitConfigService.get_enabled_configs(db_session) == {}


class TestCreate:
    def test_creates_config(self, db_session: Session):
        config = _create_config(db_session)
        assert config.id is not None
        assert config.endpoint_type == "auth_login"
        assert config.limit_string == "5/minute"
        assert config.enabled is True
        assert config.updated_by == 1

    def test_creates_disabled_config(self, db_session: Session):
        config = _create_config(db_session, enabled=False)
        assert config.enabled is False


class TestUpdate:
    def test_updates_limit_string(self, db_session: Session):
        _create_config(db_session, endpoint_type="auth_login")
        update = RateLimitConfigUpdate(limit_string="10/minute")
        result = RateLimitConfigService.update(db_session, "auth_login", update, user_id=2)
        assert result is not None
        assert result.limit_string == "10/minute"
        assert result.updated_by == 2

    def test_updates_description(self, db_session: Session):
        _create_config(db_session, endpoint_type="auth_login")
        update = RateLimitConfigUpdate(description="Updated desc")
        result = RateLimitConfigService.update(db_session, "auth_login", update, user_id=1)
        assert result.description == "Updated desc"

    def test_updates_enabled_flag(self, db_session: Session):
        _create_config(db_session, endpoint_type="auth_login", enabled=True)
        update = RateLimitConfigUpdate(enabled=False)
        result = RateLimitConfigService.update(db_session, "auth_login", update, user_id=1)
        assert result.enabled is False

    def test_returns_none_when_not_found(self, db_session: Session):
        update = RateLimitConfigUpdate(limit_string="1/minute")
        assert RateLimitConfigService.update(db_session, "nope", update, user_id=1) is None

    def test_partial_update_preserves_other_fields(self, db_session: Session):
        _create_config(
            db_session,
            endpoint_type="auth_login",
            limit_string="5/minute",
            description="Original",
        )
        update = RateLimitConfigUpdate(description="New desc")
        result = RateLimitConfigService.update(db_session, "auth_login", update, user_id=1)
        assert result.limit_string == "5/minute"
        assert result.description == "New desc"


class TestDelete:
    def test_deletes_existing(self, db_session: Session):
        _create_config(db_session, endpoint_type="auth_login")
        assert RateLimitConfigService.delete(db_session, "auth_login") is True
        assert RateLimitConfigService.get_by_endpoint_type(db_session, "auth_login") is None

    def test_returns_false_when_not_found(self, db_session: Session):
        assert RateLimitConfigService.delete(db_session, "nope") is False


class TestSeedDefaults:
    def test_seeds_when_empty(self, db_session: Session):
        RateLimitConfigService.seed_defaults(db_session)
        configs = list(RateLimitConfigService.get_all(db_session))
        assert len(configs) >= 10  # At least the default entries

    def test_does_not_seed_twice(self, db_session: Session):
        RateLimitConfigService.seed_defaults(db_session)
        count_first = len(list(RateLimitConfigService.get_all(db_session)))
        RateLimitConfigService.seed_defaults(db_session)
        count_second = len(list(RateLimitConfigService.get_all(db_session)))
        assert count_first == count_second

    def test_all_seeded_configs_are_enabled(self, db_session: Session):
        RateLimitConfigService.seed_defaults(db_session)
        configs = list(RateLimitConfigService.get_all(db_session))
        assert all(c.enabled for c in configs)
