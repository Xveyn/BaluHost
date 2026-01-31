"""Pluggy hook specifications for BaluHost.

Defines all hook points that plugins can implement.
Uses the pluggy library for type-safe hook management.
"""
import pluggy
from typing import Optional

# Create the BaluHost hook specification marker
hookspec = pluggy.HookspecMarker("baluhost")

# Create the hook implementation marker for plugins to use
hookimpl = pluggy.HookimplMarker("baluhost")


class BaluHostHookSpec:
    """Hook specifications for BaluHost plugin system.

    Plugins implement these hooks to respond to system events.
    All hooks are called with firstresult=False by default,
    meaning all registered implementations will be called.
    """

    # =========================================================================
    # File Events
    # =========================================================================

    @hookspec
    def on_file_uploaded(
        self,
        path: str,
        user_id: int,
        size: int,
        content_type: Optional[str] = None,
    ) -> None:
        """Called after a file is successfully uploaded.

        Args:
            path: Relative path to the uploaded file
            user_id: ID of the user who uploaded the file
            size: Size of the file in bytes
            content_type: MIME type of the file (if available)
        """

    @hookspec
    def on_file_deleted(
        self,
        path: str,
        user_id: int,
    ) -> None:
        """Called after a file is deleted.

        Args:
            path: Relative path to the deleted file
            user_id: ID of the user who deleted the file
        """

    @hookspec
    def on_file_moved(
        self,
        old_path: str,
        new_path: str,
        user_id: int,
    ) -> None:
        """Called after a file is moved or renamed.

        Args:
            old_path: Original path of the file
            new_path: New path of the file
            user_id: ID of the user who moved the file
        """

    @hookspec
    def on_file_downloaded(
        self,
        path: str,
        user_id: int,
    ) -> None:
        """Called when a file is downloaded.

        Args:
            path: Path to the downloaded file
            user_id: ID of the user downloading (0 for public shares)
        """

    # =========================================================================
    # User Events
    # =========================================================================

    @hookspec
    def on_user_login(
        self,
        user_id: int,
        username: str,
        ip: str,
        user_agent: Optional[str] = None,
    ) -> None:
        """Called after a successful user login.

        Args:
            user_id: ID of the logged-in user
            username: Username of the logged-in user
            ip: IP address of the login request
            user_agent: Browser/client user agent string
        """

    @hookspec
    def on_user_logout(
        self,
        user_id: int,
        username: str,
    ) -> None:
        """Called when a user logs out.

        Args:
            user_id: ID of the user
            username: Username of the user
        """

    @hookspec
    def on_user_created(
        self,
        user_id: int,
        username: str,
        role: str,
    ) -> None:
        """Called when a new user account is created.

        Args:
            user_id: ID of the new user
            username: Username of the new user
            role: Role assigned to the user (admin/user)
        """

    @hookspec
    def on_user_deleted(
        self,
        user_id: int,
        username: str,
    ) -> None:
        """Called when a user account is deleted.

        Args:
            user_id: ID of the deleted user
            username: Username of the deleted user
        """

    # =========================================================================
    # Backup Events
    # =========================================================================

    @hookspec
    def on_backup_started(
        self,
        backup_id: str,
        backup_type: str,
    ) -> None:
        """Called when a backup operation starts.

        Args:
            backup_id: Unique identifier for the backup
            backup_type: Type of backup (full, incremental, etc.)
        """

    @hookspec
    def on_backup_completed(
        self,
        backup_id: str,
        success: bool,
        size: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Called when a backup operation completes.

        Args:
            backup_id: Unique identifier for the backup
            success: Whether the backup completed successfully
            size: Size of the backup in bytes (if successful)
            error: Error message (if failed)
        """

    # =========================================================================
    # Share Events
    # =========================================================================

    @hookspec
    def on_share_created(
        self,
        share_id: str,
        path: str,
        user_id: int,
        is_public: bool,
    ) -> None:
        """Called when a share link is created.

        Args:
            share_id: Unique identifier for the share
            path: Path to the shared file/folder
            user_id: ID of the user creating the share
            is_public: Whether the share is publicly accessible
        """

    @hookspec
    def on_share_accessed(
        self,
        share_id: str,
        path: str,
        accessor_ip: str,
    ) -> None:
        """Called when a share link is accessed.

        Args:
            share_id: Unique identifier for the share
            path: Path to the shared file/folder
            accessor_ip: IP address of the accessor
        """

    # =========================================================================
    # System Events
    # =========================================================================

    @hookspec
    def on_system_startup(self) -> None:
        """Called when the BaluHost system starts up."""

    @hookspec
    def on_system_shutdown(self) -> None:
        """Called when the BaluHost system is shutting down."""

    @hookspec
    def on_storage_threshold(
        self,
        mount: str,
        usage_percent: float,
        threshold_percent: float,
    ) -> None:
        """Called when storage usage exceeds a threshold.

        Args:
            mount: Mount point that exceeded threshold
            usage_percent: Current usage percentage
            threshold_percent: The threshold that was exceeded
        """

    # =========================================================================
    # RAID Events
    # =========================================================================

    @hookspec
    def on_raid_degraded(
        self,
        array_name: str,
        failed_disk: str,
    ) -> None:
        """Called when a RAID array becomes degraded.

        Args:
            array_name: Name of the RAID array (e.g., md0)
            failed_disk: Device path of the failed disk
        """

    @hookspec
    def on_raid_rebuild_started(
        self,
        array_name: str,
    ) -> None:
        """Called when RAID rebuild starts.

        Args:
            array_name: Name of the RAID array being rebuilt
        """

    @hookspec
    def on_raid_rebuild_completed(
        self,
        array_name: str,
        success: bool,
    ) -> None:
        """Called when RAID rebuild completes.

        Args:
            array_name: Name of the RAID array
            success: Whether rebuild completed successfully
        """

    # =========================================================================
    # SMART Events
    # =========================================================================

    @hookspec
    def on_disk_health_warning(
        self,
        disk: str,
        attribute: str,
        value: int,
        threshold: int,
    ) -> None:
        """Called when a disk health metric reaches warning level.

        Args:
            disk: Device path of the disk
            attribute: SMART attribute name
            value: Current value
            threshold: Warning threshold
        """

    # =========================================================================
    # Mobile/Device Events
    # =========================================================================

    @hookspec
    def on_device_registered(
        self,
        device_id: str,
        device_name: str,
        user_id: int,
        platform: str,
    ) -> None:
        """Called when a new device is registered.

        Args:
            device_id: Unique identifier for the device
            device_name: Human-readable device name
            user_id: ID of the user registering the device
            platform: Device platform (android, ios, desktop)
        """

    @hookspec
    def on_device_removed(
        self,
        device_id: str,
        user_id: int,
    ) -> None:
        """Called when a device is removed.

        Args:
            device_id: Unique identifier for the device
            user_id: ID of the user who owned the device
        """

    # =========================================================================
    # VPN Events
    # =========================================================================

    @hookspec
    def on_vpn_client_created(
        self,
        client_id: int,
        client_name: str,
        user_id: int,
    ) -> None:
        """Called when a VPN client configuration is created.

        Args:
            client_id: ID of the VPN client
            client_name: Name of the VPN client
            user_id: ID of the user who created it
        """

    @hookspec
    def on_vpn_client_revoked(
        self,
        client_id: int,
        user_id: int,
    ) -> None:
        """Called when a VPN client is revoked.

        Args:
            client_id: ID of the VPN client
            user_id: ID of the user who owned it
        """


def create_plugin_manager() -> pluggy.PluginManager:
    """Create and configure a new pluggy PluginManager.

    Returns:
        Configured PluginManager with BaluHost hook specs registered
    """
    pm = pluggy.PluginManager("baluhost")
    pm.add_hookspecs(BaluHostHookSpec)
    return pm
