"""
Development script to run AgentShell Desktop locally

Usage:
    python dev-server.py          # Start both servers
    python dev-server.py backend  # Start only backend
    python dev-server.py frontend # Start only frontend
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# ANSI color codes
GREEN = '\033[92m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
END = '\033[0m'

def print_header():
    print(f"""
{BLUE}{BOLD}╔══════════════════════════════════════════════════════════╗
║    AgentShell Desktop - Development Environment         ║
║                                                          ║
║    Starting backend (FastAPI) & frontend (React)...    ║
╚══════════════════════════════════════════════════════════╝{END}
    """)

def check_requirements():
    """Check if all requirements are met"""
    print(f"{BOLD}Checking requirements...{END}\n")
    
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 11):
        issues.append(f"Python 3.11+ required (have {sys.version_info.major}.{sys.version_info.minor})")
    else:
        print(f"{GREEN}✓ Python {sys.version_info.major}.{sys.version_info.minor}{END}")
    
    # Check npm
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True, check=True)
        print(f"{GREEN}✓ npm {result.stdout.strip()}{END}")
    except:
        issues.append("npm not found - install Node.js from https://nodejs.org")
    
    # Check pip packages
    try:
        import fastapi
        print(f"{GREEN}✓ FastAPI available{END}")
    except ImportError:
        issues.append("FastAPI not installed - run: pip install -r backend/requirements.txt")
    
    if issues:
        print(f"\n{RED}{BOLD}Issues found:{END}")
        for issue in issues:
            print(f"  {RED}✗ {issue}{END}")
        return False
    
    print()
    return True

def start_backend():
    backend_dir = Path(__file__).parent / "backend"
    print(f"{BLUE}[Backend]{END} Starting FastAPI server...")
    
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=backend_dir
    )
    print(f"{GREEN}✓ Backend started (PID {proc.pid}){END}")
    return proc

def start_frontend():
    time.sleep(2)  # Wait for backend
    frontend_dir = Path(__file__).parent / "desktop"
    print(f"{BLUE}[Frontend]{END} Starting React dev server...")
    
    proc = subprocess.Popen(
        ["npm", "run", "react-dev"],
        cwd=frontend_dir
    )
    print(f"{GREEN}✓ Frontend started (PID {proc.pid}){END}")
    return proc

def main():
    print_header()
    
    if not check_requirements():
        return 1
    
    backend = start_backend()
    frontend = start_frontend()
    
    print(f"""
{GREEN}{BOLD}✓ All servers running!{END}

{BOLD}URLs:{END}
  Frontend: http://localhost:3000
  Backend:  http://127.0.0.1:5000
  Docs:     http://127.0.0.1:5000/docs

{YELLOW}Press Ctrl+C to stop...{END}
    """)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Shutting down...{END}")
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        print(f"{GREEN}✓ Stopped{END}")

if __name__ == "__main__":
    sys.exit(main())
