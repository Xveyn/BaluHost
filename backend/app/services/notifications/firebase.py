"""Firebase Cloud Messaging service for push notifications."""

import json
import os
import tempfile
from typing import Optional, Dict, Any
from datetime import datetime, timezone

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("[Firebase] Warning: firebase-admin not installed. Push notifications disabled.")

from app.core.config import get_settings

# Path to credentials file (relative to backend working directory)
CREDENTIALS_FILE = os.path.join(os.getcwd(), "firebase-credentials.json")


class FirebaseService:
    """Service for sending push notifications via Firebase Cloud Messaging."""
    
    _initialized = False
    _app = None
    
    @classmethod
    def initialize(cls) -> bool:
        """
        Initialize Firebase Admin SDK.
        
        Requires firebase-credentials.json in project root or FIREBASE_CREDENTIALS_JSON env var.
        
        Returns:
            bool: True if initialized successfully, False otherwise
        """
        if not FIREBASE_AVAILABLE:
            print("[Firebase] Skipping initialization: firebase-admin not installed")
            return False
        
        if cls._initialized:
            return True
        
        try:
            settings = get_settings()
            
            # Try to load credentials from environment variable first
            credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            
            if credentials_json:
                # Parse JSON from environment variable
                cred_dict = json.loads(credentials_json)
                cred = credentials.Certificate(cred_dict)
                print("[Firebase] Loaded credentials from environment variable")
            else:
                # Try to load from file
                cred_path = os.path.join(os.getcwd(), "firebase-credentials.json")
                if not os.path.exists(cred_path):
                    print(f"[Firebase] Credentials file not found: {cred_path}")
                    print("[Firebase] Set FIREBASE_CREDENTIALS_JSON env var or create firebase-credentials.json")
                    return False
                
                cred = credentials.Certificate(cred_path)
                print(f"[Firebase] Loaded credentials from: {cred_path}")
            
            # Initialize Firebase Admin SDK
            cls._app = firebase_admin.initialize_app(cred)
            cls._initialized = True
            print("[Firebase] ✅ Initialized successfully")
            return True
            
        except Exception as e:
            print(f"[Firebase] ❌ Initialization failed: {e}")
            return False
    
    @classmethod
    def is_available(cls) -> bool:
        """Check if Firebase is available and initialized."""
        return FIREBASE_AVAILABLE and cls._initialized
    
    @classmethod
    def send_notification(
        cls,
        device_token: str,
        title: str,
        body: str,
        category: str = "system",
        priority: int = 0,
        notification_id: Optional[int] = None,
        action_url: Optional[str] = None,
        notification_type: str = "info",
    ) -> Dict[str, Any]:
        """Send a general push notification via FCM.

        Args:
            device_token: FCM registration token
            title: Notification title
            body: Notification body text
            category: Notification category (raid, smart, backup, etc.)
            priority: Priority level (0-3)
            notification_id: Optional notification DB id
            action_url: Optional deep link URL
            notification_type: Type (info, warning, critical)

        Returns:
            dict with success, message_id, error keys
        """
        if not cls.is_available():
            return {
                "success": False,
                "message_id": None,
                "error": "Firebase not initialized",
            }

        try:
            channel_map = {
                "critical": "alerts_critical",
                "warning": "alerts_warning",
                "info": "alerts_info",
            }
            channel_id = channel_map.get(notification_type, "alerts_info")

            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data={
                    "type": "notification",
                    "notification_id": str(notification_id or 0),
                    "category": category,
                    "priority": str(priority),
                    "action_url": action_url or "",
                },
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#38bdf8",
                        sound="default",
                        channel_id=channel_id,
                    ),
                ),
                token=device_token,
            )
            response = messaging.send(message)
            return {
                "success": True,
                "message_id": response,
                "error": None,
            }

        except messaging.UnregisteredError:
            return {
                "success": False,
                "message_id": None,
                "error": "unregistered",
            }
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": str(e),
            }

    @classmethod
    def send_expiration_warning(
        cls,
        device_token: str,
        device_name: str,
        expires_at: datetime,
        warning_type: str,
        server_url: str
    ) -> Dict[str, Any]:
        """
        Send device expiration warning notification.
        
        Args:
            device_token: FCM registration token
            device_name: User-friendly device name
            expires_at: When the device authorization expires
            warning_type: "7_days", "3_days", or "1_hour"
            server_url: BaluHost server URL for deep linking
            
        Returns:
            dict: {
                "success": bool,
                "message_id": str or None,
                "error": str or None
            }
        """
        if not cls.is_available():
            return {
                "success": False,
                "message_id": None,
                "error": "Firebase not initialized"
            }
        
        try:
            # Build notification content based on warning type
            warning_messages = {
                "7_days": {
                    "title": "⏰ Geräte-Autorisierung läuft bald ab",
                    "body": f"Dein Gerät '{device_name}' läuft in 7 Tagen ab. Tippe hier, um zu verlängern.",
                    "days_left": 7
                },
                "3_days": {
                    "title": "⚠️ Geräte-Autorisierung läuft in 3 Tagen ab",
                    "body": f"Dein Gerät '{device_name}' läuft bald ab! Tippe hier, um zu verlängern.",
                    "days_left": 3
                },
                "1_hour": {
                    "title": "🚨 Geräte-Autorisierung läuft in 1 Stunde ab!",
                    "body": f"Dein Gerät '{device_name}' läuft gleich ab! Jetzt verlängern.",
                    "days_left": 0
                }
            }
            
            msg_config = warning_messages.get(warning_type)
            if not msg_config:
                return {
                    "success": False,
                    "message_id": None,
                    "error": f"Invalid warning_type: {warning_type}"
                }
            
            # Build FCM message with data payload for Android
            message = messaging.Message(
                notification=messaging.Notification(
                    title=msg_config["title"],
                    body=msg_config["body"]
                ),
                data={
                    "type": "expiration_warning",
                    "warning_type": warning_type,
                    "device_name": device_name,
                    "expires_at": expires_at.isoformat(),
                    "days_left": str(msg_config["days_left"]),
                    "action": "renew_device",
                    "deep_link": f"{server_url}/mobile-devices"
                },
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#38bdf8",  # sky-400
                        sound="default",
                        channel_id="device_expiration"
                    )
                ),
                token=device_token
            )
            
            # Send message
            response = messaging.send(message)
            
            print(f"[Firebase] ✅ Notification sent: {response}")
            return {
                "success": True,
                "message_id": response,
                "error": None
            }
            
        except messaging.UnregisteredError:
            print(f"[Firebase] ⚠️ Device token no longer valid (unregistered)")
            return {
                "success": False,
                "message_id": None,
                "error": "Device token unregistered"
            }
        except Exception as e:
            print(f"[Firebase] ❌ Failed to send notification: {e}")
            return {
                "success": False,
                "message_id": None,
                "error": str(e)
            }
    
    @classmethod
    def send_device_removed_notification(
        cls,
        device_token: str,
        device_name: str
    ) -> Dict[str, Any]:
        """
        Send notification when device is removed/deactivated.
        
        Args:
            device_token: FCM registration token
            device_name: User-friendly device name
            
        Returns:
            dict: Response with success status
        """
        if not cls.is_available():
            return {
                "success": False,
                "message_id": None,
                "error": "Firebase not initialized"
            }
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="❌ Gerät deautorisiert",
                    body=f"Dein Gerät '{device_name}' wurde aus BaluHost entfernt."
                ),
                data={
                    "type": "device_removed",
                    "device_name": device_name,
                    "action": "logout"
                },
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#ef4444",  # red-500
                        sound="default",
                        channel_id="device_status"
                    )
                ),
                token=device_token
            )
            
            response = messaging.send(message)
            
            print(f"[Firebase] ✅ Device removed notification sent: {response}")
            return {
                "success": True,
                "message_id": response,
                "error": None
            }
            
        except Exception as e:
            print(f"[Firebase] ❌ Failed to send device removed notification: {e}")
            return {
                "success": False,
                "message_id": None,
                "error": str(e)
            }
    
    @classmethod
    def verify_token(cls, device_token: str) -> bool:
        """
        Verify if an FCM token is valid.

        Args:
            device_token: FCM registration token to verify

        Returns:
            bool: True if token is valid, False otherwise
        """
        if not cls.is_available():
            return False

        try:
            # Try to send a dry-run message
            message = messaging.Message(
                data={"type": "token_verification"},
                token=device_token
            )

            messaging.send(message, dry_run=True)
            return True

        except messaging.UnregisteredError:
            return False
        except Exception as e:
            print(f"[Firebase] Token verification failed: {e}")
            return False

    @classmethod
    def reset(cls) -> None:
        """Reset Firebase SDK — delete app instance and clear state."""
        if FIREBASE_AVAILABLE and cls._app is not None:
            try:
                firebase_admin.delete_app(cls._app)
                print("[Firebase] App deleted for re-initialization")
            except Exception as e:
                print(f"[Firebase] Warning during app deletion: {e}")
        cls._app = None
        cls._initialized = False

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """
        Get Firebase configuration status (no secrets exposed).

        Returns:
            dict with configuration metadata
        """
        file_exists = os.path.exists(CREDENTIALS_FILE)
        env_var_set = bool(os.getenv("FIREBASE_CREDENTIALS_JSON"))

        # Determine credentials source
        credentials_source: Optional[str] = None
        if env_var_set:
            credentials_source = "env_var"
        elif file_exists:
            credentials_source = "file"

        # Extract project_id and client_email from available source
        project_id: Optional[str] = None
        client_email: Optional[str] = None

        try:
            cred_data = None
            if env_var_set:
                cred_data = json.loads(os.getenv("FIREBASE_CREDENTIALS_JSON", "{}"))
            elif file_exists:
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    cred_data = json.load(f)

            if cred_data:
                project_id = cred_data.get("project_id")
                client_email = cred_data.get("client_email")
        except (json.JSONDecodeError, OSError):
            pass

        # Get file upload timestamp
        uploaded_at: Optional[str] = None
        if file_exists:
            try:
                mtime = os.path.getmtime(CREDENTIALS_FILE)
                uploaded_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            except OSError:
                pass

        return {
            "configured": credentials_source is not None,
            "initialized": cls._initialized,
            "project_id": project_id,
            "client_email": client_email,
            "credentials_source": credentials_source,
            "file_exists": file_exists,
            "uploaded_at": uploaded_at,
            "sdk_installed": FIREBASE_AVAILABLE,
        }

    @classmethod
    def save_credentials(cls, json_str: str) -> Dict[str, Any]:
        """
        Save Firebase credentials JSON to file and re-initialize.

        Args:
            json_str: Valid Firebase service account JSON string

        Returns:
            dict with success status and project_id
        """
        cred_data = json.loads(json_str)
        project_id = cred_data.get("project_id", "unknown")

        # Atomic write: tempfile + os.replace
        parent_dir = os.path.dirname(CREDENTIALS_FILE)
        fd, tmp_path = tempfile.mkstemp(
            dir=parent_dir, prefix=".firebase-cred.tmp.", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cred_data, f, indent=2)
            os.replace(tmp_path, CREDENTIALS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        print(f"[Firebase] Credentials saved for project: {project_id}")

        # Re-initialize with new credentials
        cls.reset()
        initialized = cls.initialize()

        return {
            "success": True,
            "project_id": project_id,
            "message": f"Credentials saved and {'initialized' if initialized else 'saved (SDK not available)'}",
        }

    @classmethod
    def delete_credentials(cls) -> bool:
        """
        Delete Firebase credentials file and reset SDK.

        Returns:
            True if file was deleted, False if it didn't exist
        """
        cls.reset()

        if os.path.exists(CREDENTIALS_FILE):
            os.unlink(CREDENTIALS_FILE)
            print("[Firebase] Credentials file deleted")
            return True

        return False
