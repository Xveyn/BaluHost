"""Notification scheduler for device expiration warnings."""

from datetime import datetime, timedelta
from typing import List, Tuple
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.mobile import MobileDevice, ExpirationNotification
from app.services.firebase_service import FirebaseService
from app.core.config import get_settings


class NotificationScheduler:
    """Schedule and send device expiration warning notifications."""
    
    # Warning thresholds (how far before expiration to send notification)
    WARNING_THRESHOLDS = {
        "7_days": timedelta(days=7),
        "3_days": timedelta(days=3),
        "1_hour": timedelta(hours=1)
    }
    
    @classmethod
    def check_and_send_warnings(cls, db: Session) -> dict:
        """
        Check all devices for approaching expiration and send notifications.
        
        This method should be called periodically (e.g., every hour via APScheduler).
        
        Args:
            db: Database session
            
        Returns:
            dict: Statistics about notifications sent
        """
        print(f"\n[NotificationScheduler] Starting expiration check at {datetime.utcnow()}")
        
        stats = {
            "checked": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # Get all active devices with expiration dates and push tokens
            devices = db.query(MobileDevice).filter(
                MobileDevice.is_active == True,
                MobileDevice.expires_at.isnot(None),
                MobileDevice.push_token.isnot(None)
            ).all()
            
            stats["checked"] = len(devices)
            print(f"[NotificationScheduler] Found {len(devices)} devices to check")
            
            now = datetime.utcnow()
            
            for device in devices:
                try:
                    # Check each warning threshold
                    for warning_type, threshold in cls.WARNING_THRESHOLDS.items():
                        warning_time = device.expires_at - threshold
                        
                        # Check if we should send this warning
                        should_send, reason = cls._should_send_warning(
                            db=db,
                            device=device,
                            warning_type=warning_type,
                            warning_time=warning_time,
                            now=now
                        )
                        
                        if should_send:
                            # Send notification
                            result = cls._send_warning(
                                db=db,
                                device=device,
                                warning_type=warning_type
                            )
                            
                            if result["success"]:
                                stats["sent"] += 1
                                print(f"[NotificationScheduler] ✅ Sent {warning_type} warning to {device.device_name}")
                            else:
                                stats["failed"] += 1
                                stats["errors"].append({
                                    "device": device.device_name,
                                    "warning": warning_type,
                                    "error": result.get("error")
                                })
                                print(f"[NotificationScheduler] ❌ Failed to send {warning_type} to {device.device_name}: {result.get('error')}")
                        else:
                            stats["skipped"] += 1
                            if reason:
                                print(f"[NotificationScheduler] ⏭️ Skipped {warning_type} for {device.device_name}: {reason}")
                
                except Exception as e:
                    stats["failed"] += 1
                    stats["errors"].append({
                        "device": device.device_name,
                        "error": str(e)
                    })
                    print(f"[NotificationScheduler] ❌ Error processing device {device.device_name}: {e}")
            
            print(f"[NotificationScheduler] ✅ Completed: {stats['sent']} sent, {stats['skipped']} skipped, {stats['failed']} failed")
            
        except Exception as e:
            print(f"[NotificationScheduler] ❌ Critical error: {e}")
            stats["errors"].append({"error": f"Critical: {str(e)}"})
        
        return stats
    
    @classmethod
    def _should_send_warning(
        cls,
        db: Session,
        device: MobileDevice,
        warning_type: str,
        warning_time: datetime,
        now: datetime
    ) -> Tuple[bool, str]:
        """
        Check if a warning should be sent for this device.
        
        Args:
            db: Database session
            device: Mobile device to check
            warning_type: Type of warning (7_days, 3_days, 1_hour)
            warning_time: When the warning should be sent
            now: Current time
            
        Returns:
            Tuple[bool, str]: (should_send, reason_if_not)
        """
        # Check if it's time to send this warning (within ±30 minutes of warning time)
        time_difference = abs((warning_time - now).total_seconds())
        grace_period = 30 * 60  # 30 minutes
        
        if time_difference > grace_period:
            # Not yet time, or too late for this warning
            return False, "Not within warning window"
        
        # Check if this warning was already sent
        existing_notification = db.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id,
            ExpirationNotification.notification_type == warning_type,
            ExpirationNotification.device_expires_at == device.expires_at
        ).first()
        
        if existing_notification:
            return False, "Warning already sent"
        
        return True, ""
    
    @classmethod
    def _send_warning(
        cls,
        db: Session,
        device: MobileDevice,
        warning_type: str
    ) -> dict:
        """
        Send expiration warning notification to device.
        
        Args:
            db: Database session
            device: Mobile device to notify
            warning_type: Type of warning (7_days, 3_days, 1_hour)
            
        Returns:
            dict: Result with success status
        """
        settings = get_settings()
        server_url = settings.mobile_server_url or "http://localhost:8000"
        
        # Send FCM notification
        result = FirebaseService.send_expiration_warning(
            device_token=device.push_token,
            device_name=device.device_name,
            expires_at=device.expires_at,
            warning_type=warning_type,
            server_url=server_url
        )
        
        # Record notification in database
        notification = ExpirationNotification(
            device_id=device.id,
            notification_type=warning_type,
            sent_at=datetime.utcnow(),
            success=result["success"],
            fcm_message_id=result.get("message_id"),
            error_message=result.get("error"),
            device_expires_at=device.expires_at
        )
        db.add(notification)
        db.commit()
        
        return result
    
    @classmethod
    def run_periodic_check(cls):
        """
        Run periodic check (called by APScheduler).
        Creates its own database session.
        """
        print(f"\n{'='*60}")
        print(f"[NotificationScheduler] Periodic check triggered")
        print(f"{'='*60}")
        
        db = SessionLocal()
        try:
            stats = cls.check_and_send_warnings(db)
            
            # Log summary
            print(f"\n[NotificationScheduler] Summary:")
            print(f"  - Devices checked: {stats['checked']}")
            print(f"  - Notifications sent: {stats['sent']}")
            print(f"  - Skipped: {stats['skipped']}")
            print(f"  - Failed: {stats['failed']}")
            
            if stats['errors']:
                print(f"\n[NotificationScheduler] Errors:")
                for error in stats['errors']:
                    print(f"  - {error}")
            
        finally:
            db.close()
