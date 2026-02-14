"""WebDAV server provider for network drive access with user isolation."""

import os
import shutil
from pathlib import Path

from wsgidav import util
from wsgidav.fs_dav_provider import FileResource, FilesystemProvider, FolderResource


class BaluHostFolderResource(FolderResource):
    """Folder resource that reports disk capacity from the storage root.

    Windows WebClient reads DAV quota properties to display drive capacity.
    The default FolderResource uses shutil.disk_usage on the subfolder path,
    which can return wrong values if the subfolder is on a different mount.
    This subclass always queries the provider's storage root so Windows
    shows the correct RAID array capacity.
    """

    def get_used_bytes(self):
        return shutil.disk_usage(self.provider._storage_root).used

    def get_available_bytes(self):
        return shutil.disk_usage(self.provider._storage_root).free

    def get_member(self, name):
        fp = os.path.join(self._file_path, name)
        path = util.join_uri(self.path, name)
        if os.path.isdir(fp):
            return BaluHostFolderResource(path, self.environ, fp)
        elif os.path.isfile(fp):
            return FileResource(path, self.environ, fp)
        return None


class BaluHostDAVProvider(FilesystemProvider):
    """WebDAV provider with per-user root isolation.

    Admin users see the entire storage root.
    Regular users see only their own home directory.

    Thread-safe because the user root is determined per-request
    from the WSGI environ dict (set by the DomainController during auth).
    """

    def __init__(self, storage_root: str):
        self._storage_root = storage_root
        Path(storage_root).mkdir(parents=True, exist_ok=True)
        super().__init__(storage_root)

    def _loc_to_file_path(self, path, environ=None):
        """Map a WebDAV path to a filesystem path, applying user isolation."""
        if environ:
            role = environ.get("baluhost.user_role", "")
            username = environ.get("wsgidav.auth.user_name", "")
            if role != "admin" and username:
                user_root = os.path.join(self._storage_root, username)
                os.makedirs(user_root, exist_ok=True)
                path_parts = path.strip("/").split("/") if path.strip("/") else []
                file_path = os.path.join(user_root, *path_parts)
                # Prevent path traversal
                file_path = os.path.normpath(file_path)
                if not file_path.startswith(user_root):
                    raise ValueError("Path traversal detected")
                return file_path
        return super()._loc_to_file_path(path, environ)

    def get_resource_inst(self, path, environ):
        """Return BaluHostFolderResource for directories so quota is correct."""
        self._count_get_resource_inst += 1
        fp = self._loc_to_file_path(path, environ)
        if not os.path.exists(fp):
            return None
        if os.path.isdir(fp):
            return BaluHostFolderResource(path, environ, fp)
        return FileResource(path, environ, fp)
