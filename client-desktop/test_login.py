"""Quick test script for login functionality."""

from sync_client import SyncConfig, BaluHostSyncClient

def test_login():
    """Test login with correct credentials."""
    config = SyncConfig()
    print(f"Server URL: {config.config['server_url']}")
    print(f"Verify SSL: {config.config.get('verify_ssl', True)}")
    
    client = BaluHostSyncClient(config)
    
    print("\nAttempting login...")
    success = client.login("admin", "changeme")
    
    if success:
        print("✅ Login successful!")
        print(f"Token saved: {config.config['token'][:50]}...")
        
        # Test device registration
        print("\nAttempting device registration...")
        reg_success = client.register_device()
        if reg_success:
            print("✅ Device registration successful!")
        else:
            print("❌ Device registration failed")
    else:
        print("❌ Login failed")

if __name__ == "__main__":
    test_login()
