"""SSH Service for remote server connectivity."""

import logging
from typing import Optional, Tuple
import paramiko
from paramiko.ssh_exception import (
    NoValidConnectionsError,
    SSHException,
    AuthenticationException,
)
import socket

logger = logging.getLogger(__name__)


class SSHService:
    """Service for SSH operations on remote servers."""
    
    SSH_TIMEOUT = 10  # seconds
    SSH_BANNER_TIMEOUT = 10
    
    @staticmethod
    def test_connection(
        host: str,
        port: int,
        username: str,
        private_key_str: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Test SSH connection to a remote server.
        
        Args:
            host: SSH hostname or IP
            port: SSH port
            username: SSH username
            private_key_str: Private key as string
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            # Create SSH client
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Parse private key
            try:
                private_key = paramiko.RSAKey.from_private_key_file(
                    private_key_str,
                    password=None
                )
            except (TypeError, AttributeError):
                # Try with string directly
                import io
                private_key = paramiko.RSAKey.from_private_key(
                    io.StringIO(private_key_str)
                )
            
            # Connect
            client.connect(
                host,
                port=port,
                username=username,
                pkey=private_key,
                timeout=SSHService.SSH_TIMEOUT,
                banner_timeout=SSHService.SSH_BANNER_TIMEOUT,
            )
            
            client.close()
            return True, None
            
        except AuthenticationException as e:
            logger.warning(f"SSH authentication failed for {username}@{host}:{port}")
            return False, "SSH authentication failed - check credentials"
        except NoValidConnectionsError as e:
            logger.warning(f"SSH connection refused for {host}:{port}")
            return False, "SSH connection refused - check host and port"
        except socket.timeout:
            logger.warning(f"SSH connection timeout for {host}:{port}")
            return False, "SSH connection timeout - check host availability"
        except SSHException as e:
            logger.error(f"SSH error: {str(e)}")
            return False, f"SSH error: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during SSH test: {str(e)}")
            return False, f"Unexpected error: {str(e)}"
    
    @staticmethod
    def execute_command(
        host: str,
        port: int,
        username: str,
        private_key_str: str,
        command: str,
    ) -> Tuple[bool, str]:
        """
        Execute a command on remote server via SSH.
        
        Args:
            host: SSH hostname or IP
            port: SSH port
            username: SSH username
            private_key_str: Private key as string
            command: Command to execute
            
        Returns:
            Tuple of (success: bool, output: str)
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Parse private key
            import io
            private_key = paramiko.RSAKey.from_private_key(
                io.StringIO(private_key_str)
            )
            
            # Connect
            client.connect(
                host,
                port=port,
                username=username,
                pkey=private_key,
                timeout=SSHService.SSH_TIMEOUT,
            )
            
            # Execute command
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")
            
            client.close()
            
            if error:
                logger.warning(f"Command error on {host}: {error}")
                return False, error
            
            return True, output
            
        except Exception as e:
            logger.error(f"Error executing command on {host}: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def start_server(
        host: str,
        port: int,
        username: str,
        private_key_str: str,
        power_on_command: str,
    ) -> Tuple[bool, str]:
        """
        Start a remote BaluHost server via SSH.
        
        Args:
            host: SSH hostname or IP
            port: SSH port
            username: SSH username
            private_key_str: Private key as string
            power_on_command: Command to start the server
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Starting remote server at {username}@{host}:{port}")
        
        # First test connection
        connected, error = SSHService.test_connection(host, port, username, private_key_str)
        if not connected:
            return False, f"Cannot connect to server: {error}"
        
        # Execute startup command
        if not power_on_command:
            return False, "No power on command configured"
        
        success, output = SSHService.execute_command(
            host, port, username, private_key_str, power_on_command
        )
        
        if success:
            logger.info(f"Server startup command sent to {host}")
            return True, "Server startup command sent successfully"
        else:
            logger.error(f"Failed to execute startup command: {output}")
            return False, f"Startup command failed: {output}"
