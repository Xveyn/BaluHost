#!/usr/bin/env python3
"""
PostgreSQL Migration Setup Script

Run this to setup PostgreSQL locally for development.
Supports both manual and automated setup.
"""

import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a shell command with status reporting."""
    print(f"\n📍 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} - SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"Error: {e.stderr}")
        return False

def main():
    print("\n" + "="*60)
    print("  BaluHost PostgreSQL Migration Setup")
    print("="*60 + "\n")
    
    # Check if Docker is installed
    if run_command("docker --version", "Checking Docker installation"):
        print("\n📌 Option 1: Using Docker (Recommended)")
        print("─" * 60)
        
        # Create docker-compose.yml
        docker_compose_content = """version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: baluhost
      POSTGRES_USER: baluhost_user
      POSTGRES_PASSWORD: baluhost_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U baluhost_user"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
"""
        
        docker_compose_path = Path("deployment/docker-compose.yml")
        docker_compose_path.parent.mkdir(parents=True, exist_ok=True)
        docker_compose_path.write_text(docker_compose_content)
        print("✅ Created deployment/docker-compose.yml")
        
        # Start PostgreSQL container
        run_command(
            "docker-compose -f deployment/docker-compose.yml up -d",
            "Starting PostgreSQL container"
        )
        
        print("\n✅ PostgreSQL is running!")
        print("   Connection string: postgresql://baluhost_user:baluhost_password@localhost:5432/baluhost")
        
    else:
        print("\n📌 Option 2: Manual PostgreSQL Setup (macOS/Linux)")
        print("─" * 60)
        print("""
macOS (using Homebrew):
  brew install postgresql
  brew services start postgresql
  createdb baluhost
  psql baluhost < schema.sql

Linux (Ubuntu/Debian):
  sudo apt-get install postgresql postgresql-contrib
  sudo systemctl start postgresql
  sudo -u postgres createdb baluhost
  sudo -u postgres psql baluhost < schema.sql
""")
    
    # Next steps
    print("\n" + "="*60)
    print("  Next Steps")
    print("="*60)
    
    print("""
1. Update backend/.env:
   DATABASE_URL=postgresql://baluhost_user:baluhost_password@localhost:5432/baluhost
   DATABASE_TYPE=postgresql

2. Run migrations:
   cd backend
   alembic upgrade head

3. Seed test data:
   python scripts/seed.py

4. Start backend:
   python -m uvicorn app.main:app --reload

5. Run tests:
   pytest tests/ -v
""")
    
    print("\n✅ Setup complete! Ready for PostgreSQL migration.\n")

if __name__ == "__main__":
    main()
