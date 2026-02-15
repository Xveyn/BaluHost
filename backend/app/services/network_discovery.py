"""
Network Discovery Service - mDNS/Bonjour Implementation
Allows automatic discovery of BaluHost servers in the local network
"""

from zeroconf import ServiceInfo, Zeroconf
import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class NetworkDiscoveryService:
    """Publishes BaluHost service via mDNS/Bonjour for automatic discovery."""
    
    def __init__(self, port: int = 8000, webdav_port: int = 8080, hostname: str = None, webdav_ssl_enabled: bool = True):
        self.port = port
        self.webdav_port = webdav_port
        self.hostname = hostname or "baluhost"  # Default to "baluhost"
        self.webdav_ssl_enabled = webdav_ssl_enabled
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.webdav_service_info: Optional[ServiceInfo] = None
        self.smb_service_info: Optional[ServiceInfo] = None
        
    def get_local_ip(self) -> str:
        """Get the local IP address of this machine."""
        try:
            # Create a socket to determine the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            logger.warning(f"Could not determine local IP: {e}")
            return "127.0.0.1"
    
    def start(self):
        """Start broadcasting the service via mDNS."""
        try:
            # Use configured hostname instead of system hostname
            hostname = self.hostname
            system_hostname = socket.gethostname()
            local_ip = self.get_local_ip()

            # Initialize Zeroconf
            self.zeroconf = Zeroconf()

            # Determine WebDAV scheme and service type based on SSL setting
            webdav_scheme = "https" if self.webdav_ssl_enabled else "http"
            webdav_service_type = "_webdavs._tcp.local." if self.webdav_ssl_enabled else "_webdav._tcp.local."

            # Register BaluHost API Service
            service_name = f"BaluHost on {system_hostname}._baluhost._tcp.local."
            self.service_info = ServiceInfo(
                "_baluhost._tcp.local.",
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    'version': '1.0.0',
                    'hostname': hostname,  # Use configured hostname in properties
                    'api': f'https://{local_ip}:{self.port}',
                    'webdav': f'{webdav_scheme}://{local_ip}:{self.webdav_port}/',
                    'description': 'BaluHost - Private Cloud Storage'
                },
                server=f"{hostname}.local."  # Use configured hostname for mDNS resolution
            )

            # Register WebDAV Service (for compatibility with native clients)
            webdav_service_name = f"BaluHost WebDAV on {system_hostname}.{webdav_service_type}"
            self.webdav_service_info = ServiceInfo(
                webdav_service_type,
                webdav_service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.webdav_port,
                properties={
                    'path': '/',
                    'txtvers': '1'
                },
                server=f"{hostname}.local."  # Use configured hostname for mDNS resolution
            )
            
            # Register SMB Service (for Samba file sharing)
            smb_service_name = f"BaluHost SMB on {system_hostname}._smb._tcp.local."
            self.smb_service_info = ServiceInfo(
                "_smb._tcp.local.",
                smb_service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=445,
                properties={
                    'path': '/',
                    'txtvers': '1'
                },
                server=f"{hostname}.local."
            )

            # Register all services
            self.zeroconf.register_service(self.service_info)
            self.zeroconf.register_service(self.webdav_service_info)
            self.zeroconf.register_service(self.smb_service_info)

            logger.info(f"✓ mDNS service started:")
            logger.info(f"  - API: https://{local_ip}:{self.port}")
            logger.info(f"  - WebDAV: {webdav_scheme}://{local_ip}:{self.webdav_port}/")
            logger.info(f"  - SMB: smb://{local_ip}/")
            logger.info(f"  - WebDAV service type: {webdav_service_type}")
            logger.info(f"  - Service name: {service_name}")
            logger.info(f"  - Discovery enabled for local network")
            
        except Exception as e:
            logger.error(f"Failed to start mDNS service: {e}")
            logger.warning("Network discovery will not be available")
    
    def stop(self):
        """Stop broadcasting the service."""
        if self.zeroconf:
            try:
                if self.service_info:
                    self.zeroconf.unregister_service(self.service_info)
                if self.webdav_service_info:
                    self.zeroconf.unregister_service(self.webdav_service_info)
                if self.smb_service_info:
                    self.zeroconf.unregister_service(self.smb_service_info)
                self.zeroconf.close()
                logger.info("mDNS service stopped")
            except Exception as e:
                logger.error(f"Error stopping mDNS service: {e}")

    def get_status(self) -> dict:
        """
        Get network discovery service status.

        Returns:
            Dict with service status information for admin dashboard
        """
        is_running = self.zeroconf is not None

        webdav_service_type = "_webdavs._tcp" if self.webdav_ssl_enabled else "_webdav._tcp"

        return {
            "is_running": is_running,
            "started_at": None,  # No start time tracking
            "uptime_seconds": None,
            "sample_count": 3 if is_running else 0,  # Three services registered
            "error_count": 0,
            "last_error": None,
            "last_error_at": None,
            "interval_seconds": None,  # Continuous broadcast
            "port": self.port,
            "webdav_port": self.webdav_port,
            "hostname": self.hostname,
            "local_ip": self.get_local_ip() if is_running else None,
            "webdav_ssl_enabled": self.webdav_ssl_enabled,
            "webdav_service_type": webdav_service_type,
            "smb_port": 445,
        }
