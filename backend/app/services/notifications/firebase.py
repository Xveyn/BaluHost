"""Firebase Cloud Messaging service for push notifications."""

import json
import os
from typing import Optional, Dict, Any
from datetime import datetime

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("[Firebase] Warning: firebase-admin not installed. Push notifications disabled.")

from app.core.config import get_settings


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
