"""Middleware to track mobile device activity and update last_seen timestamps."""

from datetime import datetime
from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import SessionLocal
from app.models.mobile import MobileDevice


class DeviceTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that updates the last_seen timestamp for mobile devices.
    
    This middleware checks for the X-Device-ID header in incoming requests
    and updates the corresponding device's last_seen timestamp in the database.
    
    This allows the web UI to show which devices are currently active/connected.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Get device ID from header
        device_id = request.headers.get("X-Device-ID")
        
        # Update last_seen if device ID is present
        if device_id:
            try:
                db: Session = SessionLocal()
                try:
                    device = db.query(MobileDevice).filter(
                        MobileDevice.id == device_id
                    ).first()
                    
                    if device:
                        device.last_seen = datetime.utcnow()
                        db.commit()
                        try:
                            print(f"[DeviceTracking] Updated last_seen for device {device_id} -> {device.last_seen.isoformat()}")
                        except Exception:
                            # printing should never fail the request
                            pass
                    else:
                        print(f"[DeviceTracking] Device {device_id} not found in DB")
                except Exception as e:
                    # Don't fail the request if last_seen update fails
                    print(f"[DeviceTracking] Error updating last_seen for device {device_id}: {e}")
                    db.rollback()
                finally:
                    db.close()
            except Exception as e:
                # Don't fail the request if DB connection fails
                print(f"[DeviceTracking] Error creating DB session: {e}")
        
        # Continue with the request
        response = await call_next(request)
        return response
