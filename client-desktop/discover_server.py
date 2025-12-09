#!/usr/bin/env python3
"""
Network Discovery Client
Automatically finds BaluHost servers in the local network
"""

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
import socket
import time
import sys


class BaluHostListener(ServiceListener):
    """Listens for BaluHost services on the network."""
    
    def __init__(self):
        self.servers = []
    
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"❌ Server removed: {name}")
    
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            # Parse addresses
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            
            # Parse properties
            props = {}
            if info.properties:
                for key, value in info.properties.items():
                    try:
                        props[key.decode('utf-8')] = value.decode('utf-8')
                    except:
                        pass
            
            server = {
                'name': name,
                'addresses': addresses,
                'port': info.port,
                'hostname': props.get('hostname', 'Unknown'),
                'api_url': props.get('api', f"https://{addresses[0]}:{info.port}"),
                'webdav_url': props.get('webdav', f"http://{addresses[0]}:8080/webdav"),
                'description': props.get('description', 'BaluHost Server')
            }
            
            self.servers.append(server)
            
            print(f"\n✅ Found BaluHost Server!")
            print(f"   Name: {server['name']}")
            print(f"   Hostname: {server['hostname']}")
            print(f"   IP Address: {', '.join(addresses)}")
            print(f"   API: {server['api_url']}")
            print(f"   WebDAV: {server['webdav_url']}")
            print(f"   Description: {server['description']}")


def discover_servers(timeout=5):
    """
    Discover BaluHost servers on the local network.
    
    Args:
        timeout: Time to wait for discovery in seconds
    
    Returns:
        List of discovered servers
    """
    print(f"🔍 Searching for BaluHost servers on local network...")
    print(f"   (Waiting {timeout} seconds for responses)\n")
    
    zeroconf = Zeroconf()
    listener = BaluHostListener()
    
    # Browse for BaluHost services
    browser = ServiceBrowser(zeroconf, "_baluhost._tcp.local.", listener)
    
    try:
        # Wait for discovery
        time.sleep(timeout)
    finally:
        zeroconf.close()
    
    return listener.servers


def main():
    """Main discovery routine."""
    timeout = 5
    if len(sys.argv) > 1:
        try:
            timeout = int(sys.argv[1])
        except ValueError:
            print(f"Invalid timeout value: {sys.argv[1]}")
            print("Usage: python discover_server.py [timeout_seconds]")
            sys.exit(1)
    
    servers = discover_servers(timeout)
    
    print("\n" + "="*50)
    print(f"Discovery Complete - Found {len(servers)} server(s)")
    print("="*50)
    
    if not servers:
        print("\n❌ No BaluHost servers found on the network.")
        print("\nTroubleshooting:")
        print("  1. Make sure BaluHost server is running")
        print("  2. Check if you're on the same network")
        print("  3. Check firewall settings")
        print("  4. Try increasing timeout: python discover_server.py 10")
    else:
        print("\n📋 Available Servers:")
        for i, server in enumerate(servers, 1):
            print(f"\n{i}. {server['hostname']}")
            print(f"   API URL: {server['api_url']}")
            print(f"   WebDAV: {server['webdav_url']}")
    
    return len(servers) > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
