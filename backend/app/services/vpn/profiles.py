"""VPN Service for managing VPN connections."""

import base64
import io
import logging
import re
import qrcode
from typing import Optional, Tuple
from app.models.vpn_profile import VPNProfile
from app.models.vpn_profile import VPNType
from app.services.vpn.encryption import VPNEncryption

logger = logging.getLogger(__name__)


class VPNService:
    """Service for VPN operations and configuration management."""

    # Conservative max payload for robust scanner compatibility.
    MAX_QR_TEXT_LENGTH = 1800
    
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

    @staticmethod
    def _build_export_content(profile: VPNProfile) -> str:
        """Build exportable config content from encrypted profile payload."""
        config_content = VPNEncryption.decrypt_vpn_config(profile.config_file_encrypted)

        if profile.vpn_type != VPNType.OPENVPN:
            return config_content

        lower = config_content.lower()
        if "<cert>" not in lower and profile.certificate_encrypted:
            certificate = VPNEncryption.decrypt_vpn_config(profile.certificate_encrypted)
            config_content = (
                f"{config_content}\n\n"
                "<cert>\n"
                f"{certificate.strip()}\n"
                "</cert>\n"
            )

        if "<key>" not in lower and profile.private_key_encrypted:
            private_key = VPNEncryption.decrypt_vpn_config(profile.private_key_encrypted)
            config_content = (
                f"{config_content}\n"
                "<key>\n"
                f"{private_key.strip()}\n"
                "</key>\n"
            )

        return config_content

    @staticmethod
    def _generate_qr_base64(payload: str) -> str:
        """Create a base64-encoded QR image from a text payload."""
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)

        buffer = io.BytesIO()
        try:
            image = qr.make_image(fill_color="black", back_color="white")
            image.save(buffer, "PNG")
        except ImportError:
            modules = qr.modules
            box = 10
            border = 4
            size = (len(modules) + 2 * border) * box
            paths = []
            for r, row in enumerate(modules):
                for c, value in enumerate(row):
                    if value:
                        x = (c + border) * box
                        y = (r + border) * box
                        paths.append(f"M{x},{y}h{box}v{box}h-{box}z")
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
                f'<rect width="{size}" height="{size}" fill="#fff"/>'
                f'<path d="{"".join(paths)}" fill="#000"/>'
                "</svg>"
            )
            buffer.write(svg.encode("utf-8"))

        return base64.b64encode(buffer.getvalue()).decode()

    @staticmethod
    def build_profile_export(profile: VPNProfile) -> dict:
        """Prepare export payload for a VPN profile with QR/download mode selection."""
        config_content = VPNService._build_export_content(profile)
        config_base64 = base64.b64encode(config_content.encode("utf-8")).decode("utf-8")
        size_bytes = len(config_content.encode("utf-8"))
        filename_ext = "conf" if profile.vpn_type == VPNType.WIREGUARD else "ovpn"
        filename = f"{profile.name.strip().replace(' ', '_')}.{filename_ext}"

        mode = "qr"
        qr_code = None
        reason = None
        if len(config_content) <= VPNService.MAX_QR_TEXT_LENGTH:
            qr_code = VPNService._generate_qr_base64(config_content)
        else:
            mode = "download"
            reason = "payload_too_large"

        return {
            "mode": mode,
            "filename": filename,
            "mime_type": "text/plain",
            "config_base64": config_base64,
            "size_bytes": size_bytes,
            "qr_code": qr_code,
            "reason": reason,
        }
