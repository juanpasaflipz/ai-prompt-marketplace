#!/usr/bin/env python3
"""Quick installation of essential dependencies"""

import subprocess
import sys

def install(package):
    """Install a package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        print(f"Failed to install {package}")
        return False

def main():
    """Install essential dependencies"""
    print("Installing essential dependencies for AI Prompt Marketplace...")
    
    # Core dependencies
    packages = [
        "fastapi==0.104.1",
        "uvicorn[standard]==0.24.0",
        "pydantic==2.5.0",
        "pydantic-settings==2.1.0",
        "sqlalchemy==2.0.23",
        "alembic==1.12.1",
        "python-jose[cryptography]==3.3.0",
        "passlib[bcrypt]==1.7.4",
        "python-multipart==0.0.6",
        "redis==5.0.1",
        "httpx==0.25.2",
        "python-dotenv==1.0.0",
    ]
    
    # Try to install PostgreSQL adapter
    if not install("psycopg2-binary==2.9.9"):
        print("Trying alternative PostgreSQL adapter...")
        install("psycopg")
    
    # Install core packages
    for package in packages:
        print(f"\nInstalling {package}...")
        install(package)
    
    # Optional packages (non-critical)
    optional = ["stripe==7.0.0", "openai==1.3.0"]
    for package in optional:
        print(f"\nTrying to install optional: {package}...")
        install(package)
    
    print("\nInstallation complete!")
    print("You can now run: make dev")

if __name__ == "__main__":
    main()