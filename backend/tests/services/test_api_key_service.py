"""Tests for ApiKeyService — focus on hard-delete semantics."""
from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.models.user import User
from app.services.api_key_service import ApiKeyService


class TestDeleteApiKey:
    """Revoking a key must remove it from the database outright."""

    def test_delete_removes_row(self, db_session: Session, admin_user: User, regular_user: User):
        api_key, _raw = ApiKeyService.create_api_key(
            db=db_session,
            name="to-delete",
            created_by_id=admin_user.id,
            target_user_id=regular_user.id,
        )
        key_id = api_key.id

        deleted = ApiKeyService.delete_api_key(db_session, key_id, admin_user.id)

        assert deleted is True
        assert db_session.query(ApiKey).filter(ApiKey.id == key_id).first() is None

    def test_delete_unknown_key_returns_false(self, db_session: Session, admin_user: User):
        assert ApiKeyService.delete_api_key(db_session, 99999, admin_user.id) is False

    def test_delete_only_for_own_keys(
        self, db_session: Session, admin_user: User, another_user: User, regular_user: User
    ):
        """A key created by one admin cannot be deleted by another user id."""
        api_key, _raw = ApiKeyService.create_api_key(
            db=db_session,
            name="owned-by-admin",
            created_by_id=admin_user.id,
            target_user_id=regular_user.id,
        )
        key_id = api_key.id

        # another_user is not the creator → no deletion
        deleted = ApiKeyService.delete_api_key(db_session, key_id, another_user.id)

        assert deleted is False
        assert db_session.query(ApiKey).filter(ApiKey.id == key_id).first() is not None

    def test_deleted_key_no_longer_validates(
        self, db_session: Session, admin_user: User, regular_user: User
    ):
        api_key, raw = ApiKeyService.create_api_key(
            db=db_session,
            name="validate-then-delete",
            created_by_id=admin_user.id,
            target_user_id=regular_user.id,
        )
        assert ApiKeyService.validate_api_key(db_session, raw) is not None

        ApiKeyService.delete_api_key(db_session, api_key.id, admin_user.id)

        assert ApiKeyService.validate_api_key(db_session, raw) is None


class TestDeleteAllForUser:
    def test_delete_all_for_user(
        self, db_session: Session, admin_user: User, regular_user: User
    ):
        for i in range(3):
            ApiKeyService.create_api_key(
                db=db_session,
                name=f"key-{i}",
                created_by_id=admin_user.id,
                target_user_id=regular_user.id,
            )

        count = ApiKeyService.delete_all_for_user(db_session, regular_user.id)

        assert count == 3
        remaining = (
            db_session.query(ApiKey)
            .filter(ApiKey.target_user_id == regular_user.id)
            .count()
        )
        assert remaining == 0
