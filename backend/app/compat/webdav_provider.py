"""WebDAV server provider for network drive access - Simplified."""

from pathlib import Path
from wsgidav.fs_dav_provider import FilesystemProvider


class BaluHostDAVProvider(FilesystemProvider):
    """
    Simplified WebDAV provider using FilesystemProvider.
    
    Provides direct filesystem access to BaluHost storage.
    Note: This is a simplified version for testing. 
    Production should implement proper user isolation.
    """
    
    def __init__(self, user_id: int = 1, db=None, root_path: str = None):
        """Initialize with user-specific root."""
        if root_path is None:
            # Use dev-storage for testing
            root_path = str(Path(__file__).parent.parent.parent.parent / "dev-storage")
        
        # Ensure root path exists
        Path(root_path).mkdir(parents=True, exist_ok=True)
        
        super().__init__(root_path)
        self.user_id = user_id
        self.db = db
