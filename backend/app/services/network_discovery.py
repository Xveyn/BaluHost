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
    
    def __init__(self, port: int = 8000, webdav_port: int = 8080):
        self.port = port
        self.webdav_port = webdav_port
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.webdav_service_info: Optional[ServiceInfo] = None
        
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
            hostname = socket.gethostname()
            local_ip = self.get_local_ip()
            
            # Initialize Zeroconf
            self.zeroconf = Zeroconf()
            
            # Register BaluHost API Service
            service_name = f"BaluHost on {hostname}._baluhost._tcp.local."
            self.service_info = ServiceInfo(
                "_baluhost._tcp.local.",
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    'version': '1.0.0',
                    'hostname': hostname,
                    'api': f'https://{local_ip}:{self.port}',
                    'webdav': f'http://{local_ip}:{self.webdav_port}/webdav',
                    'description': 'BaluHost - Private Cloud Storage'
                },
                server=f"{hostname}.local."
            )
            
            # Register WebDAV Service (for compatibility with native clients)
            webdav_service_name = f"BaluHost WebDAV on {hostname}._webdav._tcp.local."
            self.webdav_service_info = ServiceInfo(
                "_webdav._tcp.local.",
                webdav_service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.webdav_port,
                properties={
                    'path': '/webdav',
                    'txtvers': '1'
                },
                server=f"{hostname}.local."
            )
            
            # Register both services
            self.zeroconf.register_service(self.service_info)
            self.zeroconf.register_service(self.webdav_service_info)
            
            logger.info(f"✓ mDNS service started:")
            logger.info(f"  - API: https://{local_ip}:{self.port}")
            logger.info(f"  - WebDAV: http://{local_ip}:{self.webdav_port}/webdav")
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
                self.zeroconf.close()
                logger.info("mDNS service stopped")
            except Exception as e:
                logger.error(f"Error stopping mDNS service: {e}")
