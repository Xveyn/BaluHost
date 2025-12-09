"""BaluHost Desktop Sync Client - File Watcher and Auto-Sync."""

import os
import sys
import time
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from collections import defaultdict

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('baluhost_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('BaluHostSync')


class SyncConfig:
    """Configuration for the sync client."""
    
    def __init__(self, config_path: str = "sync_config.json"):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from file."""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        
        # Default configuration
        return {
            "server_url": "https://localhost:8000",
            "device_id": f"desktop-{os.getenv('COMPUTERNAME', 'unknown')}",
            "device_name": f"Desktop - {os.getenv('COMPUTERNAME', 'My Computer')}",
            "token": None,
            "sync_folders": [],
            "auto_sync": True,
            "sync_interval": 60,  # seconds
            "debounce_delay": 2,  # seconds to wait after file change
            "verify_ssl": False,  # Dev mode: accept self-signed certificates
        }
    
    def save(self):
        """Save configuration to file."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Configuration saved to {self.config_path}")
    
    def set_token(self, token: str):
        """Set authentication token."""
        self.config['token'] = token
        self.save()
    
    def add_sync_folder(self, folder_path: str):
        """Add a folder to sync."""
        if folder_path not in self.config['sync_folders']:
            self.config['sync_folders'].append(folder_path)
            self.save()
            logger.info(f"Added sync folder: {folder_path}")
    
    def remove_sync_folder(self, folder_path: str):
        """Remove a folder from sync."""
        if folder_path in self.config['sync_folders']:
            self.config['sync_folders'].remove(folder_path)
            self.save()
            logger.info(f"Removed sync folder: {folder_path}")


class BaluHostSyncClient:
    """Main sync client for BaluHost."""
    
    def __init__(self, config: SyncConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {config.config["token"]}'
        })
        # Disable SSL verification for self-signed certificates in dev mode
        self.session.verify = config.config.get('verify_ssl', True)
        self.pending_changes: Dict[str, float] = {}  # path -> timestamp
        self.syncing = False
    
    def _get_url(self, path: str) -> str:
        """Get full API URL."""
        return f"{self.config.config['server_url']}{path}"
    
    def login(self, username: str, password: str) -> bool:
        """Login to BaluHost server."""
        try:
            # Suppress SSL warnings for self-signed certificates
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = self.session.post(
                self._get_url('/api/auth/login'),
                json={'username': username, 'password': password}
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get('access_token')
                self.config.set_token(token)
                self.session.headers.update({'Authorization': f'Bearer {token}'})
                logger.info(f"Logged in as {username}")
                return True
            else:
                logger.error(f"Login failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def register_device(self) -> bool:
        """Register this device with the server."""
        try:
            response = self.session.post(
                self._get_url('/api/sync/register'),
                json={
                    'device_id': self.config.config['device_id'],
                    'device_name': self.config.config['device_name']
                }
            )
            
            if response.status_code == 200:
                logger.info(f"Device registered: {self.config.config['device_id']}")
                return True
            else:
                logger.error(f"Device registration failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Device registration error: {e}")
            return False
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """Calculate SHA256 hash of a file."""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Error hashing {file_path}: {e}")
            return None
    
    def get_file_list(self) -> List[Dict]:
        """Get list of files in sync folders."""
        file_list = []
        
        for folder in self.config.config['sync_folders']:
            folder_path = Path(folder)
            if not folder_path.exists():
                logger.warning(f"Sync folder does not exist: {folder}")
                continue
            
            for file_path in folder_path.rglob('*'):
                if file_path.is_file():
                    try:
                        stat = file_path.stat()
                        file_hash = self.calculate_file_hash(str(file_path))
                        
                        if file_hash:
                            relative_path = file_path.relative_to(folder_path)
                            file_list.append({
                                'path': str(relative_path).replace('\\', '/'),
                                'hash': file_hash,
                                'size': stat.st_size,
                                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                            })
                    except Exception as e:
                        logger.error(f"Error processing {file_path}: {e}")
        
        return file_list
    
    def detect_changes(self) -> Optional[Dict]:
        """Detect changes between local and server."""
        try:
            file_list = self.get_file_list()
            
            response = self.session.post(
                self._get_url('/api/sync/changes'),
                json={
                    'device_id': self.config.config['device_id'],
                    'file_list': file_list
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Change detection failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Change detection error: {e}")
            return None
    
    def upload_file(self, local_path: str, server_path: str):
        """Upload a file to the server."""
        try:
            with open(local_path, 'rb') as f:
                response = self.session.post(
                    self._get_url('/api/files/upload'),
                    files={'file': (os.path.basename(local_path), f)},
                    data={'path': server_path}
                )
            
            if response.status_code == 200:
                logger.info(f"Uploaded: {server_path}")
                return True
            else:
                logger.error(f"Upload failed {server_path}: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Upload error {server_path}: {e}")
            return False
    
    def download_file(self, server_path: str, local_path: str):
        """Download a file from the server."""
        try:
            # Remove leading slash if present for URL construction
            path = server_path.lstrip('/')
            response = self.session.get(
                self._get_url(f'/api/files/download/{path}')
            )
            
            if response.status_code == 200:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                logger.info(f"Downloaded: {server_path}")
                return True
            else:
                logger.error(f"Download failed {server_path}: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Download error {server_path}: {e}")
            return False
    
    def sync(self):
        """Perform a full sync."""
        if self.syncing:
            logger.info("Sync already in progress, skipping")
            return
        
        self.syncing = True
        logger.info("Starting sync...")
        
        try:
            changes = self.detect_changes()
            if not changes:
                logger.error("Failed to detect changes")
                return
            
            to_download = changes.get('to_download', [])
            to_delete = changes.get('to_delete', [])
            conflicts = changes.get('conflicts', [])
            
            logger.info(f"Changes detected - Download: {len(to_download)}, Delete: {len(to_delete)}, Conflicts: {len(conflicts)}")
            
            # Download files from server
            for item in to_download:
                server_path = item['path']
                action = item.get('action', 'add')
                
                # Find appropriate local folder
                if self.config.config['sync_folders']:
                    local_path = os.path.join(self.config.config['sync_folders'][0], server_path)
                    
                    # Create directory if needed
                    if action == 'mkdir':
                        os.makedirs(local_path, exist_ok=True)
                        logger.info(f"Created directory: {server_path}")
                    else:
                        # Download file
                        self.download_file(server_path, local_path)
            
            # Handle conflicts (simple: keep server version)
            for conflict in conflicts:
                logger.warning(f"Conflict detected: {conflict['path']} - keeping server version")
                if self.config.config['sync_folders']:
                    local_path = os.path.join(self.config.config['sync_folders'][0], conflict['path'])
                    self.download_file(conflict['path'], local_path)
            
            logger.info("Sync completed")
            
        except Exception as e:
            logger.error(f"Sync error: {e}")
        finally:
            self.syncing = False
    
    def process_pending_changes(self):
        """Process pending file changes after debounce delay."""
        current_time = time.time()
        debounce_delay = self.config.config['debounce_delay']
        
        to_process = []
        for path, timestamp in list(self.pending_changes.items()):
            if current_time - timestamp >= debounce_delay:
                to_process.append(path)
                del self.pending_changes[path]
        
        if to_process:
            logger.info(f"Processing {len(to_process)} pending changes")
            self.sync()


class SyncFileSystemEventHandler(FileSystemEventHandler):
    """Handle file system events for auto-sync."""
    
    def __init__(self, sync_client: BaluHostSyncClient):
        self.sync_client = sync_client
    
    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event."""
        if event.is_directory:
            return
        
        # Ignore temporary files
        if event.src_path.endswith(('.tmp', '.swp', '~')):
            return
        
        logger.debug(f"File event: {event.event_type} - {event.src_path}")
        
        # Add to pending changes with current timestamp
        self.sync_client.pending_changes[event.src_path] = time.time()


def main():
    """Main entry point for the sync client."""
    print("=" * 60)
    print("BaluHost Desktop Sync Client")
    print("=" * 60)
    
    # Load configuration
    config = SyncConfig()
    sync_client = BaluHostSyncClient(config)
    
    # Check if token exists
    if not config.config['token']:
        print("\nNo authentication token found. Please login:")
        username = input("Username: ")
        password = input("Password: ")
        
        if not sync_client.login(username, password):
            print("Login failed. Exiting.")
            return
    
    # Register device
    print(f"\nRegistering device: {config.config['device_id']}")
    sync_client.register_device()
    
    # Configure sync folders
    if not config.config['sync_folders']:
        print("\nNo sync folders configured.")
        while True:
            folder = input("Enter folder path to sync (or 'done' to finish): ")
            if folder.lower() == 'done':
                break
            if os.path.exists(folder):
                config.add_sync_folder(folder)
            else:
                print(f"Folder does not exist: {folder}")
    
    print(f"\nSync folders: {config.config['sync_folders']}")
    
    # Perform initial sync
    print("\nPerforming initial sync...")
    sync_client.sync()
    
    # Start file watcher
    if config.config['auto_sync']:
        print("\nStarting file watcher for auto-sync...")
        event_handler = SyncFileSystemEventHandler(sync_client)
        observer = Observer()
        
        for folder in config.config['sync_folders']:
            observer.schedule(event_handler, folder, recursive=True)
            print(f"Watching: {folder}")
        
        observer.start()
        
        try:
            while True:
                time.sleep(1)
                sync_client.process_pending_changes()
        except KeyboardInterrupt:
            print("\nStopping sync client...")
            observer.stop()
            observer.join()
    else:
        print("\nAuto-sync disabled. Use manual sync mode.")
    
    print("Sync client stopped.")


if __name__ == "__main__":
    main()
