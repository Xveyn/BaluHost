"""VPN service for WireGuard configuration and management."""

import logging
import os
import secrets
import base64
import subprocess
import tempfile
from typing import Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.vpn import VPNClient, VPNConfig
from app.schemas.vpn import VPNClientCreate, VPNConfigResponse

logger = logging.getLogger(__name__)


class VPNService:
    """Service for managing WireGuard VPN configurations."""

    # WireGuard default settings
    VPN_NETWORK = "10.8.0.0/24"
    VPN_SERVER_IP = "10.8.0.1"
    VPN_PORT = 51820
    VPN_DNS_FALLBACK = "1.1.1.1"  # Cloudflare DNS (fallback when Pi-hole is not active)

    # ------------------------------------------------------------------
    # Conditional encryption helpers
    # ------------------------------------------------------------------
    # VPN_ENCRYPTION_KEY may not be set (e.g. dev mode).  When absent we
    # fall back to storing plaintext and log a warning.

    @staticmethod
    def _encryption_available() -> bool:
        """Return True if VPN_ENCRYPTION_KEY is configured."""
        return bool(settings.vpn_encryption_key)

    @staticmethod
    def _encrypt_key(plaintext: str) -> str:
        """Encrypt *plaintext* if VPN_ENCRYPTION_KEY is available, else return as-is."""
        if not VPNService._encryption_available():
            logger.warning(
                "VPN_ENCRYPTION_KEY not set — storing VPN key in plaintext. "
                "Set VPN_ENCRYPTION_KEY in .env for production."
            )
            return plaintext
        from app.services.vpn.encryption import VPNEncryption
        return VPNEncryption.encrypt_key(plaintext)

    @staticmethod
    def _decrypt_key(stored: str) -> str:
        """Decrypt *stored* value.  Handles both encrypted and legacy plaintext values."""
        if not stored:
            return stored
        if not VPNService._encryption_available():
            # No encryption key — assume the value is plaintext.
            return stored
        from app.services.vpn.encryption import VPNEncryption
        try:
            return VPNEncryption.decrypt_key(stored)
        except Exception:
            # Value may be legacy plaintext that was never encrypted.
            # Return it as-is so existing configs keep working.
            logger.debug(
                "Could not decrypt VPN key — assuming legacy plaintext value."
            )
            return stored

    # ------------------------------------------------------------------
    # Effective endpoint / key resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _get_effective_endpoint(caller_endpoint: str) -> tuple[str, int]:
        """Get the effective endpoint hostname and port for client configs.

        Priority:
            1. ``vpn_public_endpoint`` setting (DDNS override)
            2. ``caller_endpoint`` (value supplied by the API caller)

        For the port:
            1. ``vpn_public_port`` setting (external port, e.g. port-forwarded)
            2. ``VPN_PORT`` (internal WireGuard listen port, 51820)
        """
        hostname = (
            settings.vpn_public_endpoint
            if settings.vpn_public_endpoint
            else caller_endpoint
        )
        port = (
            settings.vpn_public_port
            if settings.vpn_public_port
            else VPNService.VPN_PORT
        )
        return hostname, port

    @staticmethod
    def _get_effective_server_public_key(server_config: 'VPNConfig') -> str:
        """Get the server public key to embed in client configs.

        Priority:
            1. ``vpn_server_public_key`` setting (explicit override)
            2. DB-stored key from *server_config*
        """
        if settings.vpn_server_public_key:
            return settings.vpn_server_public_key
        return server_config.server_public_key

    # ------------------------------------------------------------------
    # Read existing server keys from running WireGuard interface
    # ------------------------------------------------------------------

    @staticmethod
    def _read_server_keys_from_interface() -> tuple[str, str] | None:
        """Read WireGuard server keys from the running wg0 interface.

        Uses ``sudo wg show wg0`` to read the private and public keys of
        the already-configured WireGuard server.  This ensures that client
        configs contain the **real** server public key instead of a freshly
        generated (and therefore wrong) one.

        Returns:
            ``(private_key, public_key)`` on success, or ``None`` if the
            interface is not running or keys cannot be read.
        """
        if settings.is_dev_mode:
            return None

        try:
            priv_result = subprocess.run(
                ["sudo", "wg", "show", "wg0", "private-key"],
                capture_output=True, text=True, timeout=5,
            )
            if priv_result.returncode != 0:
                logger.debug(
                    "Could not read wg0 private key: %s",
                    priv_result.stderr.strip(),
                )
                return None
            private_key = priv_result.stdout.strip()

            pub_result = subprocess.run(
                ["sudo", "wg", "show", "wg0", "public-key"],
                capture_output=True, text=True, timeout=5,
            )
            if pub_result.returncode != 0:
                logger.debug(
                    "Could not read wg0 public key: %s",
                    pub_result.stderr.strip(),
                )
                return None
            public_key = pub_result.stdout.strip()

            if private_key and public_key:
                logger.info("Read existing server keys from wg0 interface")
                return private_key, public_key
            return None
        except Exception as exc:
            logger.debug("Failed to read server keys from wg0: %s", exc)
            return None

    @staticmethod
    def sync_server_keys_from_interface(db: Session) -> tuple[bool, str]:
        """Sync server keys in the database from the running wg0 interface.

        Reads the actual private/public key pair from the WireGuard
        interface and updates (or creates) the ``VPNConfig`` row so that
        all future client configs use the correct server public key.

        Returns:
            ``(success, message)``
        """
        keys = VPNService._read_server_keys_from_interface()
        if keys is None:
            return False, (
                "Could not read server keys from wg0 interface. "
                "Is WireGuard running?"
            )

        private_key, public_key = keys

        server_config = db.query(VPNConfig).first()
        if not server_config:
            server_config = VPNConfig(
                server_private_key=VPNService._encrypt_key(private_key),
                server_public_key=public_key,
                server_ip=VPNService.VPN_SERVER_IP,
                server_port=VPNService.VPN_PORT,
                network_cidr=VPNService.VPN_NETWORK,
            )
            db.add(server_config)
            db.commit()
            return True, (
                f"Created server config with keys from wg0 "
                f"(public key: {public_key[:12]}…)"
            )

        old_public = server_config.server_public_key
        if old_public == public_key:
            return True, "Server public key already matches wg0 interface"

        server_config.server_private_key = VPNService._encrypt_key(private_key)
        server_config.server_public_key = public_key
        db.commit()

        logger.warning(
            "Updated server keys from wg0 — old public key %s… replaced "
            "with %s…",
            old_public[:12],
            public_key[:12],
        )
        return True, (
            f"Updated server keys from wg0 interface "
            f"(old: {old_public[:12]}…, new: {public_key[:12]}…)"
        )

    # ------------------------------------------------------------------
    # Server config generation & application
    # ------------------------------------------------------------------

    @staticmethod
    def get_lan_interface() -> str:
        """Detect the LAN interface for NAT rules.

        Uses ``vpn_lan_interface`` setting if set, otherwise auto-detects
        from the default route.  Returns ``"eth0"`` in dev mode.
        """
        if settings.vpn_lan_interface:
            return settings.vpn_lan_interface

        if settings.is_dev_mode:
            return "eth0"

        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            # e.g. "default via 192.168.178.1 dev enp9s0 proto ..."
            for part in result.stdout.split():
                idx = result.stdout.split().index(part)
                if part == "dev" and idx + 1 < len(result.stdout.split()):
                    return result.stdout.split()[idx + 1]
        except Exception as exc:
            logger.warning("Failed to detect LAN interface: %s", exc)

        return "eth0"

    @staticmethod
    def generate_server_config(db: Session) -> str:
        """Generate a WireGuard server config from database state.

        Returns the config file content as a string.
        """
        server_config = db.query(VPNConfig).first()
        if not server_config:
            raise RuntimeError("No VPN server config in database. Generate a client first to initialise keys.")

        server_private = VPNService._decrypt_key(server_config.server_private_key)
        lan_iface = VPNService.get_lan_interface()

        lines: list[str] = [
            "[Interface]",
            f"PrivateKey = {server_private}",
            f"Address = {server_config.server_ip}/24",
            f"ListenPort = {server_config.server_port}",
        ]

        if settings.vpn_include_lan:
            # Extract VPN subnet from server IP (e.g. 10.8.0.1 -> 10.8.0.0/24)
            vpn_parts = server_config.server_ip.rsplit(".", 1)
            vpn_subnet = f"{vpn_parts[0]}.0/24"

            lines.append(
                f"PostUp = sysctl -w net.ipv4.ip_forward=1; "
                f"iptables -A FORWARD -i wg0 -j ACCEPT; "
                f"iptables -A FORWARD -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT; "
                f"iptables -t nat -A POSTROUTING -s {vpn_subnet} -o {lan_iface} -j MASQUERADE"
            )
            lines.append(
                f"PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; "
                f"iptables -D FORWARD -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT; "
                f"iptables -t nat -D POSTROUTING -s {vpn_subnet} -o {lan_iface} -j MASQUERADE"
            )

        # Add active client peers
        clients = db.query(VPNClient).filter(VPNClient.is_active == True).all()
        for client in clients:
            lines.append("")
            lines.append("[Peer]")
            lines.append(f"PublicKey = {client.public_key}")
            psk = VPNService._decrypt_key(client.preshared_key)
            if psk:
                lines.append(f"PresharedKey = {psk}")
            lines.append(f"AllowedIPs = {client.assigned_ip}/32")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def apply_server_config(db: Session) -> tuple[bool, str]:
        """Generate and apply WireGuard server config.

        In dev mode the config is generated but not written/applied.
        Returns ``(success, message)``.
        """
        try:
            config_content = VPNService.generate_server_config(db)
        except RuntimeError as exc:
            return False, str(exc)

        if settings.is_dev_mode:
            logger.info("Dev mode: generated WireGuard server config (not applying)")
            return True, "Server config generated (dev mode — not applied)"

        config_path = settings.vpn_config_path

        # Write config via sudo tee (backend user needs sudoers entry)
        try:
            proc = subprocess.run(
                ["sudo", "tee", config_path],
                input=config_content, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                return False, f"Failed to write config: {proc.stderr.strip()}"
            # Restrict permissions
            subprocess.run(
                ["sudo", "chmod", "600", config_path],
                capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:
            return False, f"Failed to write config: {exc}"

        # Check if wg0 interface is already up
        try:
            check = subprocess.run(
                ["ip", "link", "show", "wg0"],
                capture_output=True, text=True, timeout=5,
            )
            wg0_up = check.returncode == 0
        except Exception:
            wg0_up = False

        if wg0_up:
            # Live-reload without disconnecting clients
            # wg syncconf needs a stripped config (no Interface Address/PostUp/PostDown)
            try:
                strip_proc = subprocess.run(
                    ["sudo", "wg-quick", "strip", "wg0"],
                    capture_output=True, text=True, timeout=10,
                )
                if strip_proc.returncode != 0:
                    return False, f"wg-quick strip failed: {strip_proc.stderr.strip()}"

                # Write stripped config to temp file for syncconf
                with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp:
                    tmp.write(strip_proc.stdout)
                    tmp_path = tmp.name

                try:
                    sync_proc = subprocess.run(
                        ["sudo", "wg", "syncconf", "wg0", tmp_path],
                        capture_output=True, text=True, timeout=10,
                    )
                    if sync_proc.returncode != 0:
                        return False, f"wg syncconf failed: {sync_proc.stderr.strip()}"
                finally:
                    os.unlink(tmp_path)

                logger.info("WireGuard server config synced (live reload)")
                return True, "Server config synced (live reload)"
            except Exception as exc:
                return False, f"Failed to sync config: {exc}"
        else:
            # Interface not up — start it
            try:
                up_proc = subprocess.run(
                    ["sudo", "wg-quick", "up", "wg0"],
                    capture_output=True, text=True, timeout=15,
                )
                if up_proc.returncode != 0:
                    return False, f"wg-quick up failed: {up_proc.stderr.strip()}"
                logger.info("WireGuard interface wg0 started")
                return True, "Server config applied and wg0 started"
            except Exception as exc:
                return False, f"Failed to start wg0: {exc}"

    @staticmethod
    def _try_apply_server_config(db: Session) -> None:
        """Best-effort server config sync.  Errors are logged, not raised."""
        try:
            success, message = VPNService.apply_server_config(db)
            if not success:
                logger.warning("Server config sync failed: %s", message)
            else:
                logger.info("Server config sync: %s", message)
        except Exception as exc:
            logger.warning("Server config sync error: %s", exc)

    @staticmethod
    def get_vpn_dns(db: Optional['Session'] = None) -> str:
        """Get the DNS server to use for VPN clients.

        Returns Pi-hole IP (10.8.0.1) if Pi-hole is active and configured as VPN DNS,
        otherwise falls back to Cloudflare (1.1.1.1).
        """
        try:
            from app.services.pihole.service import PiholeService
            if db is None:
                from app.core.database import SessionLocal
                db = SessionLocal()
                try:
                    return PiholeService(db).get_vpn_dns()
                finally:
                    db.close()
            return PiholeService(db).get_vpn_dns()
        except Exception:
            return VPNService.VPN_DNS_FALLBACK

    @staticmethod
    def generate_wireguard_keypair() -> tuple[str, str]:
        """
        Generate WireGuard private and public key pair.
        
        Returns:
            tuple[str, str]: (private_key, public_key)
        """
        if settings.is_dev_mode:
            # Mock keys in dev mode
            private_key = base64.b64encode(secrets.token_bytes(32)).decode()
            public_key = base64.b64encode(secrets.token_bytes(32)).decode()
            return private_key, public_key
        
        try:
            # Generate private key
            private_result = subprocess.run(
                ["wg", "genkey"],
                capture_output=True,
                text=True,
                check=True
            )
            private_key = private_result.stdout.strip()
            
            # Generate public key from private key
            public_result = subprocess.run(
                ["wg", "pubkey"],
                input=private_key,
                capture_output=True,
                text=True,
                check=True
            )
            public_key = public_result.stdout.strip()
            
            return private_key, public_key
        except Exception as e:
            raise RuntimeError(f"Failed to generate WireGuard keys: {str(e)}")
    
    @staticmethod
    def generate_preshared_key() -> str:
        """Generate WireGuard preshared key for additional security."""
        if settings.is_dev_mode:
            return base64.b64encode(secrets.token_bytes(32)).decode()
        
        try:
            result = subprocess.run(
                ["wg", "genpsk"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception as e:
            raise RuntimeError(f"Failed to generate preshared key: {str(e)}")
    
    @staticmethod
    def get_next_client_ip(db: Session) -> str:
        """
        Get the next available client IP address.
        
        Args:
            db: Database session
            
        Returns:
            str: Next available IP (e.g., "10.8.0.2")
        """
        # Get all assigned IPs
        clients = db.query(VPNClient).filter(VPNClient.is_active == True).all()
        assigned_ips = {client.assigned_ip for client in clients}
        
        # Find first available IP (starting from .2, .1 is server)
        for i in range(2, 255):
            ip = f"10.8.0.{i}"
            if ip not in assigned_ips:
                return ip
        
        raise RuntimeError("No available IP addresses in VPN network")
    
    @staticmethod
    def create_client_config(
        db: Session,
        user_id: int,
        device_name: str,
        server_public_endpoint: str,
    ) -> VPNConfigResponse:
        """
        Create a new WireGuard client configuration.

        Args:
            db: Database session
            user_id: User ID
            device_name: Device name (e.g., "iPhone 13 Pro")
            server_public_endpoint: Server public IP or domain

        Returns:
            VPNConfigResponse: Configuration with client keys and config file
        """
        # Strip protocol and port from endpoint URL to get bare hostname/IP
        from urllib.parse import urlparse
        endpoint = server_public_endpoint
        if "://" in endpoint:
            parsed = urlparse(endpoint)
            endpoint = parsed.hostname or endpoint
        elif ":" in endpoint:
            endpoint = endpoint.split(":")[0]
        server_public_endpoint = endpoint

        # Generate client keypair
        client_private, client_public = VPNService.generate_wireguard_keypair()
        preshared_key = VPNService.generate_preshared_key()
        
        # Get next available IP
        client_ip = VPNService.get_next_client_ip(db)
        
        # Get or create server config
        server_config = db.query(VPNConfig).first()
        if not server_config:
            # Try to read keys from the already-running WireGuard interface
            # so that client configs contain the real server public key.
            existing_keys = VPNService._read_server_keys_from_interface()
            if existing_keys:
                server_private, server_public = existing_keys
                logger.info("Using existing wg0 server keys for new VPN config")
            else:
                server_private, server_public = VPNService.generate_wireguard_keypair()
                logger.info("Generated new server keypair (no running wg0 found)")
            server_config = VPNConfig(
                server_private_key=VPNService._encrypt_key(server_private),
                server_public_key=server_public,
                server_ip=VPNService.VPN_SERVER_IP,
                server_port=VPNService.VPN_PORT,
                network_cidr=VPNService.VPN_NETWORK,
            )
            db.add(server_config)
            db.commit()
            db.refresh(server_config)
        else:
            # Verify stored key matches the running interface and auto-correct
            # if they diverge (e.g. wg0 was re-keyed or DB was seeded wrong).
            if not settings.is_dev_mode:
                existing_keys = VPNService._read_server_keys_from_interface()
                if (
                    existing_keys
                    and existing_keys[1] != server_config.server_public_key
                ):
                    logger.warning(
                        "DB server public key (%s…) does not match wg0 "
                        "interface (%s…). Updating DB to match running "
                        "interface.",
                        server_config.server_public_key[:12],
                        existing_keys[1][:12],
                    )
                    server_config.server_private_key = (
                        VPNService._encrypt_key(existing_keys[0])
                    )
                    server_config.server_public_key = existing_keys[1]
                    db.commit()
                    db.refresh(server_config)

        # Create client entry — encrypt preshared key before storing
        client = VPNClient(
            user_id=user_id,
            device_name=device_name,
            public_key=client_public,
            preshared_key=VPNService._encrypt_key(preshared_key),
            assigned_ip=client_ip,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_handshake=None,
        )
        db.add(client)
        db.commit()
        db.refresh(client)

        # Resolve effective endpoint and server public key
        effective_hostname, effective_port = VPNService._get_effective_endpoint(
            server_public_endpoint
        )
        effective_server_pubkey = VPNService._get_effective_server_public_key(
            server_config
        )

        # Build AllowedIPs — VPN network + optional LAN
        allowed_ips = VPNService.VPN_NETWORK
        if settings.vpn_include_lan and settings.vpn_lan_network:
            allowed_ips += f", {settings.vpn_lan_network}"

        # Generate WireGuard config file — use plaintext keys (not the encrypted DB values)
        config_content = f"""[Interface]
PrivateKey = {client_private}
Address = {client_ip}/32
DNS = {VPNService.get_vpn_dns(db)}

[Peer]
PublicKey = {effective_server_pubkey}
PresharedKey = {preshared_key}
Endpoint = {effective_hostname}:{effective_port}
AllowedIPs = {allowed_ips}
PersistentKeepalive = 25
"""

        # Sync server config so the new client peer is active immediately
        VPNService._try_apply_server_config(db)

        # Base64 encode config for QR code
        config_base64 = base64.b64encode(config_content.encode()).decode()

        return VPNConfigResponse(
            client_id=client.id,
            device_name=device_name,
            assigned_ip=client_ip,
            client_public_key=client_public,
            server_public_key=effective_server_pubkey,
            server_endpoint=f"{effective_hostname}:{effective_port}",
            config_content=config_content,
            config_base64=config_base64,
        )
    
    @staticmethod
    def get_client_by_id(db: Session, client_id: int) -> Optional[VPNClient]:
        """Get VPN client by ID."""
        return db.query(VPNClient).filter(VPNClient.id == client_id).first()
    
    @staticmethod
    def get_clients_by_user(db: Session, user_id: int) -> list[VPNClient]:
        """Get all VPN clients for a user."""
        return db.query(VPNClient).filter(VPNClient.user_id == user_id).all()
    
    @staticmethod
    def revoke_client(db: Session, client_id: int) -> bool:
        """Revoke a VPN client (deactivate)."""
        client = VPNService.get_client_by_id(db, client_id)
        if not client:
            return False

        client.is_active = False
        db.commit()
        VPNService._try_apply_server_config(db)
        return True
    
    @staticmethod
    def delete_client(db: Session, client_id: int) -> bool:
        """Delete a VPN client permanently."""
        client = VPNService.get_client_by_id(db, client_id)
        if not client:
            return False

        db.delete(client)
        db.commit()
        VPNService._try_apply_server_config(db)
        return True
    
    @staticmethod
    def get_server_config(db: Session) -> Optional[VPNConfig]:
        """Get the WireGuard server configuration."""
        return db.query(VPNConfig).first()
    
    @staticmethod
    def update_last_handshake(db: Session, client_id: int) -> None:
        """Update the last handshake timestamp for a client."""
        client = VPNService.get_client_by_id(db, client_id)
        if client:
            client.last_handshake = datetime.now(timezone.utc)
            db.commit()
    
    @staticmethod
    def regenerate_client_config(
        db: Session,
        client_id: int,
        server_public_endpoint: str,
    ) -> VPNConfigResponse:
        """Regenerate a client config with the current server public key.

        Because the client private key is not stored in the database, a new
        client keypair is generated.  The client must import the returned
        config to replace their old (broken) one.

        Args:
            db: Database session
            client_id: Existing VPN client ID
            server_public_endpoint: Server public IP or domain

        Returns:
            VPNConfigResponse with fresh client keys and correct server key
        """
        from urllib.parse import urlparse

        client = db.query(VPNClient).filter(VPNClient.id == client_id).first()
        if not client:
            raise ValueError("VPN client not found")

        server_config = db.query(VPNConfig).first()
        if not server_config:
            raise RuntimeError("No VPN server config in database")

        # Strip protocol/port from endpoint
        endpoint = server_public_endpoint
        if "://" in endpoint:
            parsed = urlparse(endpoint)
            endpoint = parsed.hostname or endpoint
        elif ":" in endpoint:
            endpoint = endpoint.split(":")[0]

        # Generate new client keypair (private key is never stored)
        client_private, client_public = VPNService.generate_wireguard_keypair()

        # Reuse existing preshared key
        preshared_key = VPNService._decrypt_key(client.preshared_key)

        # Update client public key in DB
        client.public_key = client_public
        db.commit()
        db.refresh(client)

        # Resolve effective endpoint and server public key
        effective_hostname, effective_port = VPNService._get_effective_endpoint(
            endpoint
        )
        effective_server_pubkey = VPNService._get_effective_server_public_key(
            server_config
        )

        # Build AllowedIPs
        allowed_ips = VPNService.VPN_NETWORK
        if settings.vpn_include_lan and settings.vpn_lan_network:
            allowed_ips += f", {settings.vpn_lan_network}"

        config_content = f"""[Interface]
PrivateKey = {client_private}
Address = {client.assigned_ip}/32
DNS = {VPNService.get_vpn_dns(db)}

[Peer]
PublicKey = {effective_server_pubkey}
PresharedKey = {preshared_key}
Endpoint = {effective_hostname}:{effective_port}
AllowedIPs = {allowed_ips}
PersistentKeepalive = 25
"""

        # Sync server config with updated client public key
        VPNService._try_apply_server_config(db)

        config_base64 = base64.b64encode(config_content.encode()).decode()

        return VPNConfigResponse(
            client_id=client.id,
            device_name=client.device_name,
            assigned_ip=client.assigned_ip,
            client_public_key=client_public,
            server_public_key=effective_server_pubkey,
            server_endpoint=f"{effective_hostname}:{effective_port}",
            config_content=config_content,
            config_base64=config_base64,
        )

    # ------------------------------------------------------------------
    # Fritz!Box methods — delegated to FritzBoxVPNService
    # ------------------------------------------------------------------
    # These are kept as static methods on VPNService for backward
    # compatibility.  The actual implementation lives in
    # app.services.vpn.fritzbox.FritzBoxVPNService.

    from app.services.vpn.fritzbox import FritzBoxVPNService as _FB  # noqa: E402

    parse_fritzbox_config = staticmethod(_FB.parse_fritzbox_config)
    upload_fritzbox_config = staticmethod(_FB.upload_fritzbox_config)
    get_fritzbox_config_base64 = staticmethod(_FB.get_fritzbox_config_base64)
    get_active_fritzbox_config = staticmethod(_FB.get_active_fritzbox_config)
    delete_fritzbox_config = staticmethod(_FB.delete_fritzbox_config)

    del _FB  # Clean up class namespace
