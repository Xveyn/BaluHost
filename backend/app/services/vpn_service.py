"""VPN Service for managing VPN connections."""

import logging
import re
from typing import Optional, Tuple
from app.models.vpn_profile import VPNType

logger = logging.getLogger(__name__)


class VPNService:
    """Service for VPN operations and configuration management."""
    
    @staticmethod
    def validate_openvpn_config(config_content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate OpenVPN configuration file format.
        
        Args:
            config_content: Content of .ovpn file
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        try:
            if not config_content or not config_content.strip():
                return False, "Configuration file is empty"
            
            # Check for essential OpenVPN directives
            if "client" not in config_content.lower():
                logger.warning("OpenVPN config missing 'client' directive")
                return False, "Invalid OpenVPN config - missing 'client' directive"
            
            # Check for protocol (tcp or udp)
            if not re.search(r"proto\s+(tcp|udp)", config_content, re.IGNORECASE):
                logger.warning("OpenVPN config missing 'proto' directive")
                return False, "Invalid OpenVPN config - missing 'proto' directive"
            
            # Check for remote host
            if not re.search(r"remote\s+\S+", config_content, re.IGNORECASE):
                logger.warning("OpenVPN config missing 'remote' directive")
                return False, "Invalid OpenVPN config - missing 'remote' directive"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error validating OpenVPN config: {str(e)}")
            return False, f"Validation error: {str(e)}"
    
    @staticmethod
    def validate_wireguard_config(config_content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate WireGuard configuration file format.
        
        Args:
            config_content: Content of .conf file
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        try:
            if not config_content or not config_content.strip():
                return False, "Configuration file is empty"
            
            # Check for required sections
            if "[Interface]" not in config_content:
                logger.warning("WireGuard config missing '[Interface]' section")
                return False, "Invalid WireGuard config - missing '[Interface]' section"
            
            if "[Peer]" not in config_content:
                logger.warning("WireGuard config missing '[Peer]' section")
                return False, "Invalid WireGuard config - missing '[Peer]' section"
            
            # Check for PrivateKey in Interface section
            if "PrivateKey" not in config_content:
                logger.warning("WireGuard config missing 'PrivateKey'")
                return False, "Invalid WireGuard config - missing 'PrivateKey'"
            
            # Check for Endpoint in Peer section
            if "Endpoint" not in config_content:
                logger.warning("WireGuard config missing 'Endpoint'")
                return False, "Invalid WireGuard config - missing 'Endpoint'"
            
            # Check for PublicKey in Peer section
            if "PublicKey" not in config_content:
                logger.warning("WireGuard config missing 'PublicKey'")
                return False, "Invalid WireGuard config - missing 'PublicKey'"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error validating WireGuard config: {str(e)}")
            return False, f"Validation error: {str(e)}"
    
    @staticmethod
    def validate_config(
        vpn_type: VPNType,
        config_content: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate VPN configuration based on type.
        
        Args:
            vpn_type: Type of VPN (openvpn, wireguard)
            config_content: Configuration file content
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if vpn_type == VPNType.OPENVPN:
            return VPNService.validate_openvpn_config(config_content)
        elif vpn_type == VPNType.WIREGUARD:
            return VPNService.validate_wireguard_config(config_content)
        elif vpn_type == VPNType.CUSTOM:
            # Custom VPNs just need non-empty config
            if not config_content or not config_content.strip():
                return False, "Configuration file is empty"
            return True, None
        else:
            return False, f"Unsupported VPN type: {vpn_type}"
    
    @staticmethod
    def extract_server_info(config_content: str, vpn_type: VPNType) -> Optional[str]:
        """
        Extract VPN server address from configuration.
        
        Args:
            config_content: Configuration file content
            vpn_type: Type of VPN
            
        Returns:
            Server address or None
        """
        try:
            if vpn_type == VPNType.OPENVPN:
                # Extract from 'remote' directive
                match = re.search(r"remote\s+(\S+)", config_content, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            elif vpn_type == VPNType.WIREGUARD:
                # Extract from 'Endpoint' in [Peer] section
                match = re.search(r"Endpoint\s*=\s*(\S+)", config_content, re.IGNORECASE)
                if match:
                    server = match.group(1)
                    # Remove port if present
                    return server.split(":")[0] if ":" in server else server
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting server info: {str(e)}")
            return None
    
    @staticmethod
    def check_certificate_required(config_content: str, vpn_type: VPNType) -> bool:
        """
        Check if VPN configuration requires client certificate.
        
        Args:
            config_content: Configuration file content
            vpn_type: Type of VPN
            
        Returns:
            True if certificate is required
        """
        if vpn_type == VPNType.OPENVPN:
            # Check if config has <ca>, <cert>, <key> tags or references
            if "<ca>" in config_content or "ca " in config_content.lower():
                return True
            if "<cert>" in config_content or "cert " in config_content.lower():
                return True
            return False
        
        elif vpn_type == VPNType.WIREGUARD:
            # WireGuard uses inline keys, no separate certificate needed
            return False
        
        return False
