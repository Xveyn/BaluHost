"""Integration tests for remote server start feature (server and VPN profiles)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

from app.models import ServerProfile, VPNProfile, VPNType
from app.main import app
from app.services.vpn_encryption import VPNEncryption


@pytest.fixture
def client_with_user(db_session, client):
    """Get test client and login as test user."""
    # Login first
    response = client.post(
        "/auth/login",
        json={"username": "testuser", "password": "Test@1234"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # Add token to client headers
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


class TestServerProfileAPI:
    """Tests for Server Profile API endpoints."""
    
    def test_create_server_profile_success(self, client_with_user, db_session, test_user):
        """Test creating a server profile with valid SSH key."""
        # Sample RSA private key for testing
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        response = client_with_user.post(
            "/api/server-profiles",
            json={
                "name": "Home NAS",
                "ssh_host": "192.168.1.100",
                "ssh_port": 22,
                "ssh_username": "admin",
                "ssh_private_key": ssh_key,
                "power_on_command": "systemctl start baluhost-backend",
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Home NAS"
        assert data["ssh_host"] == "192.168.1.100"
        assert data["ssh_port"] == 22
        assert "id" in data
        assert "created_at" in data
    
    def test_create_server_profile_invalid_key(self, client_with_user):
        """Test creating server profile with invalid SSH key."""
        response = client_with_user.post(
            "/api/server-profiles",
            json={
                "name": "Bad Profile",
                "ssh_host": "192.168.1.100",
                "ssh_port": 22,
                "ssh_username": "admin",
                "ssh_private_key": "not-a-valid-key",
            }
        )
        
        assert response.status_code == 400
        assert "PRIVATE KEY" in response.json()["detail"]
    
    def test_list_server_profiles(self, client_with_user, db_session, test_user):
        """Test listing server profiles for current user."""
        # Create a profile directly
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="Test Server",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.get("/api/server-profiles")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["name"] == "Test Server"
    
    def test_get_server_profile(self, client_with_user, db_session, test_user):
        """Test getting a specific server profile."""
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="Office Server",
            ssh_host="192.168.0.1",
            ssh_port=2222,
            ssh_username="admin",
            ssh_key_encrypted=encrypted_key,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.get(f"/api/server-profiles/{profile.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == profile.id
        assert data["name"] == "Office Server"
        assert data["ssh_port"] == 2222
    
    def test_get_nonexistent_server_profile(self, client_with_user):
        """Test getting a profile that doesn't exist."""
        response = client_with_user.get("/api/server-profiles/99999")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_update_server_profile(self, client_with_user, db_session, test_user):
        """Test updating a server profile."""
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="Old Name",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.put(
            f"/api/server-profiles/{profile.id}",
            json={"name": "New Name"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
    
    def test_delete_server_profile(self, client_with_user, db_session, test_user):
        """Test deleting a server profile."""
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="To Delete",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
        )
        db_session.add(profile)
        db_session.commit()
        profile_id = profile.id
        
        response = client_with_user.delete(f"/api/server-profiles/{profile_id}")
        
        assert response.status_code == 204
        
        # Verify deleted
        response = client_with_user.get(f"/api/server-profiles/{profile_id}")
        assert response.status_code == 404
    
    @patch("app.services.ssh_service.SSHService.test_connection")
    def test_check_ssh_connection_success(self, mock_ssh, client_with_user, db_session, test_user):
        """Test SSH connectivity check endpoint."""
        mock_ssh.return_value = (True, None)
        
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="Test",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.post(f"/api/server-profiles/{profile.id}/check-connectivity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ssh_reachable"] is True
        assert data["error_message"] is None
    
    @patch("app.services.ssh_service.SSHService.test_connection")
    def test_check_ssh_connection_failure(self, mock_ssh, client_with_user, db_session, test_user):
        """Test SSH connectivity check with failure."""
        mock_ssh.return_value = (False, "Connection refused")
        
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="Test",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.post(f"/api/server-profiles/{profile.id}/check-connectivity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ssh_reachable"] is False
        assert "Connection refused" in data["error_message"]
    
    @patch("app.services.ssh_service.SSHService.start_server")
    def test_start_remote_server(self, mock_start, client_with_user, db_session, test_user):
        """Test remote server startup endpoint."""
        mock_start.return_value = (True, "Server startup initiated")
        
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        profile = ServerProfile(
            user_id=test_user.id,
            name="Test",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
            power_on_command="systemctl start baluhost-backend",
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.post(f"/api/server-profiles/{profile.id}/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["profile_id"] == profile.id
        assert data["status"] == "starting"


class TestVPNProfileAPI:
    """Tests for VPN Profile API endpoints."""
    
    def test_create_openvpn_profile(self, client_with_user, db_session, test_user):
        """Test creating an OpenVPN profile."""
        ovpn_config = """client
dev tun
proto udp
remote vpn.example.com 1194
cipher AES-256-CBC
"""
        
        # Use form data with files
        from io import BytesIO
        response = client_with_user.post(
            "/api/vpn-profiles",
            data={
                "name": "My OpenVPN",
                "vpn_type": "openvpn",
                "auto_connect": "false",
                "description": "Home VPN",
            },
            files={"config_file": ("config.ovpn", BytesIO(ovpn_config.encode()))}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My OpenVPN"
        assert data["vpn_type"] == "openvpn"
        assert "id" in data
    
    def test_create_vpn_profile_invalid_type(self, client_with_user):
        """Test creating VPN profile with invalid type."""
        from io import BytesIO
        
        ovpn_config = "client\nremote vpn.example.com 1194\n"
        
        response = client_with_user.post(
            "/api/vpn-profiles",
            data={
                "name": "Bad VPN",
                "vpn_type": "invalid_type",
            },
            files={"config_file": ("config.ovpn", BytesIO(ovpn_config.encode()))}
        )
        
        assert response.status_code == 400
        assert "Invalid VPN type" in response.json()["detail"]
    
    def test_create_vpn_profile_invalid_config(self, client_with_user):
        """Test creating VPN profile with invalid config."""
        from io import BytesIO
        
        bad_config = "this is not a valid openvpn config"
        
        response = client_with_user.post(
            "/api/vpn-profiles",
            data={
                "name": "Bad Config",
                "vpn_type": "openvpn",
            },
            files={"config_file": ("config.ovpn", BytesIO(bad_config.encode()))}
        )
        
        assert response.status_code == 400
        assert "Invalid VPN configuration" in response.json()["detail"]
    
    def test_list_vpn_profiles(self, client_with_user, db_session, test_user):
        """Test listing VPN profiles."""
        config = "client\nremote vpn.example.com 1194\nproto udp\n"
        encrypted_config = VPNEncryption.encrypt_vpn_config(config)
        
        profile = VPNProfile(
            user_id=test_user.id,
            name="Test VPN",
            vpn_type=VPNType.OPENVPN,
            config_file_encrypted=encrypted_config,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.get("/api/vpn-profiles")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["name"] == "Test VPN"
    
    def test_get_vpn_profile(self, client_with_user, db_session, test_user):
        """Test getting a specific VPN profile."""
        config = "client\nremote vpn.example.com 1194\nproto udp\n"
        encrypted_config = VPNEncryption.encrypt_vpn_config(config)
        
        profile = VPNProfile(
            user_id=test_user.id,
            name="Office VPN",
            vpn_type=VPNType.OPENVPN,
            config_file_encrypted=encrypted_config,
            auto_connect=True,
            description="Office network access",
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.get(f"/api/vpn-profiles/{profile.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == profile.id
        assert data["name"] == "Office VPN"
        assert data["auto_connect"] is True
    
    def test_delete_vpn_profile(self, client_with_user, db_session, test_user):
        """Test deleting a VPN profile."""
        config = "client\nremote vpn.example.com 1194\nproto udp\n"
        encrypted_config = VPNEncryption.encrypt_vpn_config(config)
        
        profile = VPNProfile(
            user_id=test_user.id,
            name="To Delete",
            vpn_type=VPNType.OPENVPN,
            config_file_encrypted=encrypted_config,
        )
        db_session.add(profile)
        db_session.commit()
        profile_id = profile.id
        
        response = client_with_user.delete(f"/api/vpn-profiles/{profile_id}")
        
        assert response.status_code == 204
        
        # Verify deleted
        response = client_with_user.get(f"/api/vpn-profiles/{profile_id}")
        assert response.status_code == 404
    
    def test_vpn_connection_test(self, client_with_user, db_session, test_user):
        """Test VPN connection validation."""
        config = "client\nremote vpn.example.com 1194\nproto udp\n"
        encrypted_config = VPNEncryption.encrypt_vpn_config(config)
        
        profile = VPNProfile(
            user_id=test_user.id,
            name="Test VPN",
            vpn_type=VPNType.OPENVPN,
            config_file_encrypted=encrypted_config,
        )
        db_session.add(profile)
        db_session.commit()
        
        response = client_with_user.post(f"/api/vpn-profiles/{profile.id}/test-connection")
        
        assert response.status_code == 200
        data = response.json()
        assert data["profile_id"] == profile.id
        assert data["connected"] is True
        assert data["error_message"] is None


class TestServerVPNProfileIntegration:
    """Tests for integration between server and VPN profiles."""
    
    def test_create_server_with_vpn_profile(self, client_with_user, db_session, test_user):
        """Test creating server profile linked to VPN profile."""
        # Create VPN profile first
        config = "client\nremote vpn.example.com 1194\nproto udp\n"
        encrypted_config = VPNEncryption.encrypt_vpn_config(config)
        
        vpn_profile = VPNProfile(
            user_id=test_user.id,
            name="Work VPN",
            vpn_type=VPNType.OPENVPN,
            config_file_encrypted=encrypted_config,
        )
        db_session.add(vpn_profile)
        db_session.commit()
        
        # Create server profile with VPN
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        response = client_with_user.post(
            "/api/server-profiles",
            json={
                "name": "Remote Office NAS",
                "ssh_host": "192.168.1.100",
                "ssh_port": 22,
                "ssh_username": "admin",
                "ssh_private_key": ssh_key,
                "vpn_profile_id": vpn_profile.id,
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["vpn_profile_id"] == vpn_profile.id
    
    def test_delete_vpn_profile_cascades_to_servers(self, client_with_user, db_session, test_user):
        """Test that deleting VPN profile clears reference from servers."""
        # Create VPN profile
        config = "client\nremote vpn.example.com 1194\nproto udp\n"
        encrypted_config = VPNEncryption.encrypt_vpn_config(config)
        
        vpn_profile = VPNProfile(
            user_id=test_user.id,
            name="To Delete",
            vpn_type=VPNType.OPENVPN,
            config_file_encrypted=encrypted_config,
        )
        db_session.add(vpn_profile)
        db_session.commit()
        
        # Create server using this VPN
        ssh_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z+4rqGr1+...truncated...
-----END RSA PRIVATE KEY-----"""
        
        encrypted_key = VPNEncryption.encrypt_ssh_private_key(ssh_key)
        server = ServerProfile(
            user_id=test_user.id,
            name="Server with VPN",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_username="user",
            ssh_key_encrypted=encrypted_key,
            vpn_profile_id=vpn_profile.id,
        )
        db_session.add(server)
        db_session.commit()
        server_id = server.id
        
        # Delete VPN profile
        response = client_with_user.delete(f"/api/vpn-profiles/{vpn_profile.id}")
        assert response.status_code == 204
        
        # Verify server still exists but VPN reference is cleared
        db_session.refresh(server)
        assert server.vpn_profile_id is None
