"""Start WebDAV server for network drive mounting."""

import sys
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cheroot import wsgi
from app.compat.webdav_asgi import create_webdav_standalone_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webdav_server")


def main():
    """Start the WebDAV server."""
    print("=" * 60)
    print("BaluHost WebDAV Server")
    print("=" * 60)
    print("")
    print("Network Drive Mount Points:")
    print("  Windows:  \\\\localhost:8080\\")
    print("  macOS:    http://localhost:8080/")
    print("  Linux:    http://localhost:8080/")
    print("")
    print("Default Credentials:")
    print("  Username: admin")
    print("  Password: password")
    print("")
    print("=" * 60)
    print("")
    
    # Create WebDAV app
    app = create_webdav_standalone_app()
    
    # Create Cheroot WSGI server
    server = wsgi.Server(
        bind_addr=('0.0.0.0', 8080),
        wsgi_app=app
    )
    
    try:
        logger.info("Starting WebDAV server on http://0.0.0.0:8080")
        server.start()
    except KeyboardInterrupt:
        print("\nStopping WebDAV server...")
        server.stop()


if __name__ == "__main__":
    main()
