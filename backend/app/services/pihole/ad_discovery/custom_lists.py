"""Custom blocklist management for Ad Discovery."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Directory for generated adlist files
_LISTS_DIR = Path(__file__).resolve().parents[4] / "data" / "ad_discovery_lists"


class CustomListsService:
    """Manages custom blocklists: CRUD, adlist file generation, Pi-hole deployment."""

    def __init__(self, lists_dir: Optional[Path] = None) -> None:
        self._lists_dir = lists_dir or _LISTS_DIR

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_list(
        self, db: Session, name: str, description: str = ""
    ) -> "AdDiscoveryCustomList":
        """Create a new custom blocklist.

        Args:
            db: Database session.
            name: Unique list name.
            description: Optional description.

        Returns:
            The newly created AdDiscoveryCustomList instance.

        Raises:
            sqlalchemy.exc.IntegrityError: If a list with the same name exists.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        now = datetime.now(timezone.utc)
        new_list = AdDiscoveryCustomList(
            name=name,
            description=description,
            domain_count=0,
            created_at=now,
            updated_at=now,
            deployed=False,
            adlist_token=str(uuid.uuid4()),
        )
        db.add(new_list)
        db.commit()
        db.refresh(new_list)
        return new_list

    def get_list(
        self, db: Session, list_id: int
    ) -> Optional["AdDiscoveryCustomList"]:
        """Retrieve a custom list by ID.

        Args:
            db: Database session.
            list_id: Primary key of the list.

        Returns:
            AdDiscoveryCustomList or None if not found.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        return (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )

    def get_all_lists(self, db: Session) -> list["AdDiscoveryCustomList"]:
        """Retrieve all custom blocklists.

        Args:
            db: Database session.

        Returns:
            List of all AdDiscoveryCustomList instances.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        return db.query(AdDiscoveryCustomList).all()

    def update_list(
        self,
        db: Session,
        list_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional["AdDiscoveryCustomList"]:
        """Update the name and/or description of a custom list.

        Args:
            db: Database session.
            list_id: ID of the list to update.
            name: New name (unchanged if None).
            description: New description (unchanged if None).

        Returns:
            Updated AdDiscoveryCustomList, or None if not found.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if not lst:
            return None
        if name is not None:
            lst.name = name
        if description is not None:
            lst.description = description
        lst.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(lst)
        return lst

    def delete_list(self, db: Session, list_id: int) -> bool:
        """Delete a custom list and all its domains (cascade).

        Args:
            db: Database session.
            list_id: ID of the list to delete.

        Returns:
            True if the list was deleted, False if not found.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if not lst:
            return False
        db.delete(lst)
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Domain management
    # ------------------------------------------------------------------

    def add_domains(
        self,
        db: Session,
        list_id: int,
        domains: list[str],
        comment: str = "",
    ) -> int:
        """Add domains to a custom list, skipping duplicates.

        Args:
            db: Database session.
            list_id: Target list ID.
            domains: Raw domain strings (will be lowercased/stripped).
            comment: Optional comment stored with each domain.

        Returns:
            Number of newly added (non-duplicate) domains.

        Raises:
            ValueError: If the list does not exist.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList, AdDiscoveryCustomListDomain

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if not lst:
            raise ValueError(f"List {list_id} not found")

        existing: set[str] = {
            row.domain
            for row in db.query(AdDiscoveryCustomListDomain.domain).filter(
                AdDiscoveryCustomListDomain.list_id == list_id
            ).all()
        }

        added = 0
        now = datetime.now(timezone.utc)
        for raw in domains:
            domain = raw.lower().strip()
            if domain and domain not in existing:
                db.add(
                    AdDiscoveryCustomListDomain(
                        list_id=list_id,
                        domain=domain,
                        added_at=now,
                        comment=comment,
                    )
                )
                existing.add(domain)
                added += 1

        lst.domain_count = len(existing)
        lst.updated_at = now
        db.commit()
        return added

    def remove_domain(self, db: Session, list_id: int, domain: str) -> bool:
        """Remove a single domain from a custom list.

        Args:
            db: Database session.
            list_id: Target list ID.
            domain: Domain to remove (will be lowercased/stripped).

        Returns:
            True if removed, False if the domain was not found.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList, AdDiscoveryCustomListDomain

        normalised = domain.lower().strip()
        row = (
            db.query(AdDiscoveryCustomListDomain)
            .filter(
                AdDiscoveryCustomListDomain.list_id == list_id,
                AdDiscoveryCustomListDomain.domain == normalised,
            )
            .first()
        )
        if not row:
            return False

        db.delete(row)
        db.flush()  # Apply the delete so the subsequent count is accurate.

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if lst:
            remaining = (
                db.query(AdDiscoveryCustomListDomain)
                .filter(AdDiscoveryCustomListDomain.list_id == list_id)
                .count()
            )
            lst.domain_count = remaining
            lst.updated_at = datetime.now(timezone.utc)

        db.commit()
        return True

    # ------------------------------------------------------------------
    # Adlist file generation
    # ------------------------------------------------------------------

    def generate_adlist_content(self, db: Session, list_id: int) -> str:
        """Generate the text content for an adlist file.

        The output starts with a header comment block followed by all
        domains in alphabetical order, one per line.

        Args:
            db: Database session.
            list_id: Source list ID.

        Returns:
            Formatted adlist string ending with a newline.

        Raises:
            ValueError: If the list does not exist.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList, AdDiscoveryCustomListDomain

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if not lst:
            raise ValueError(f"List {list_id} not found")

        domain_rows = (
            db.query(AdDiscoveryCustomListDomain.domain)
            .filter(AdDiscoveryCustomListDomain.list_id == list_id)
            .order_by(AdDiscoveryCustomListDomain.domain)
            .all()
        )

        lines = [
            f"# BaluHost Custom Blocklist: {lst.name}",
            f"# Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"# Domains: {len(domain_rows)}",
            "",
        ]
        lines.extend(row.domain for row in domain_rows)
        return "\n".join(lines) + "\n"

    def generate_adlist_file(self, db: Session, list_id: int) -> Path:
        """Write the adlist content to disk and return the file path.

        Args:
            db: Database session.
            list_id: Source list ID.

        Returns:
            Path to the written adlist file.
        """
        content = self.generate_adlist_content(db, list_id)
        self._lists_dir.mkdir(parents=True, exist_ok=True)
        path = self._lists_dir / f"{list_id}.txt"
        path.write_text(content, encoding="utf-8")
        return path

    def export_list(self, db: Session, list_id: int) -> bytes:
        """Export a custom list as UTF-8 bytes suitable for file download.

        Args:
            db: Database session.
            list_id: Source list ID.

        Returns:
            UTF-8 encoded adlist content.
        """
        return self.generate_adlist_content(db, list_id).encode("utf-8")

    # ------------------------------------------------------------------
    # Pi-hole deployment
    # ------------------------------------------------------------------

    async def deploy_to_pihole(
        self,
        db: Session,
        list_id: int,
        base_url: str,
        pihole_backend,
    ) -> str:
        """Deploy a custom list as an adlist in Pi-hole.

        Writes the adlist file to disk, registers the URL with Pi-hole,
        and triggers a gravity update.

        Args:
            db: Database session.
            list_id: ID of the list to deploy.
            base_url: Public base URL of the BaluHost API (e.g. ``http://nas.local:3001``).
            pihole_backend: Pi-hole protocol backend instance.

        Returns:
            The adlist URL registered with Pi-hole.

        Raises:
            ValueError: If the list does not exist.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if not lst:
            raise ValueError(f"List {list_id} not found")

        self.generate_adlist_file(db, list_id)

        adlist_url = (
            f"{base_url}/api/pihole/ad-discovery/custom-lists/{list_id}/adlist.txt?token={lst.adlist_token}"
        )

        await pihole_backend.add_adlist(adlist_url, comment=f"BaluHost: {lst.name}")
        await pihole_backend.update_gravity()

        lst.deployed = True
        lst.adlist_url = adlist_url
        lst.updated_at = datetime.now(timezone.utc)
        db.commit()

        return adlist_url

    async def undeploy_from_pihole(
        self,
        db: Session,
        list_id: int,
        pihole_backend,
    ) -> None:
        """Remove a custom list's adlist from Pi-hole.

        Args:
            db: Database session.
            list_id: ID of the list to undeploy.
            pihole_backend: Pi-hole protocol backend instance.

        Raises:
            ValueError: If the list does not exist.
        """
        from app.models.ad_discovery import AdDiscoveryCustomList

        lst = (
            db.query(AdDiscoveryCustomList)
            .filter(AdDiscoveryCustomList.id == list_id)
            .first()
        )
        if not lst:
            raise ValueError(f"List {list_id} not found")

        if lst.adlist_url:
            await pihole_backend.remove_adlist(lst.adlist_url)
            await pihole_backend.update_gravity()

        lst.deployed = False
        lst.adlist_url = None
        lst.updated_at = datetime.now(timezone.utc)
        db.commit()
