#!/usr/bin/env python3
"""
AgentShell Desktop - Development Server Manager

This script manages both the backend (FastAPI) and frontend (Electron/React) servers
for development. It starts both servers in separate processes.
"""

import subprocess
import sys
import time
import os
from pathlib import Path

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_banner():
    print(f"""
{Colors.OKBLUE}{Colors.BOLD}
╔════════════════════════════════════════════════════════════╗
║       AgentShell Desktop - Development Server              ║
║                                                            ║
║  Starting both backend (FastAPI) and frontend (React)...  ║
╚════════════════════════════════════════════════════════════╝
{Colors.ENDC}
    """)

def start_backend():
    """Start the FastAPI backend server"""
    print(f"{Colors.OKCYAN}[Backend]{Colors.ENDC} Starting FastAPI server on port 5000...")
    
    backend_path = Path(__file__).parent / "backend"
    
    if not backend_path.exists():
        print(f"{Colors.FAIL}[Backend]{Colors.ENDC} Backend directory not found!")
        return None
    
    try:
        proc = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=backend_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"{Colors.OKGREEN}[Backend]{Colors.ENDC} FastAPI server started (PID: {proc.pid})")
        return proc
    except Exception as e:
        print(f"{Colors.FAIL}[Backend]{Colors.ENDC} Failed to start backend: {e}")
        return None

def start_frontend():
    """Start the React development server"""
    print(f"{Colors.OKCYAN}[Frontend]{Colors.ENDC} Waiting for backend to be ready...")
    time.sleep(3)  # Wait for backend to initialize
    
    print(f"{Colors.OKCYAN}[Frontend]{Colors.ENDC} Starting React dev server on port 3000...")
    
    frontend_path = Path(__file__).parent / "desktop"
    
    if not frontend_path.exists():
        print(f"{Colors.FAIL}[Frontend]{Colors.ENDC} Frontend directory not found!")
        return None
    
    try:
        # Check if npm is available
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.FAIL}[Frontend]{Colors.ENDC} npm not found! Please install Node.js")
        return None
    
    try:
        proc = subprocess.Popen(
            ["npm", "run", "react-dev"],
            cwd=frontend_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"{Colors.OKGREEN}[Frontend]{Colors.ENDC} React dev server started (PID: {proc.pid})")
        return proc
    except Exception as e:
        print(f"{Colors.FAIL}[Frontend]{Colors.ENDC} Failed to start frontend: {e}")
        return None

def main():
    print_banner()
    
    # Check prerequisites
    print(f"{Colors.BOLD}Checking prerequisites...{Colors.ENDC}")
    
    # Check Python
    if sys.version_info < (3, 11):
        print(f"{Colors.FAIL}✗ Python 3.11+ required (you have {sys.version_info.major}.{sys.version_info.minor})")
        return 1
    print(f"{Colors.OKGREEN}✓ Python {sys.version_info.major}.{sys.version_info.minor}{Colors.ENDC}")
    
    # Check npm
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True, check=True)
        print(f"{Colors.OKGREEN}✓ npm {result.stdout.strip()}{Colors.ENDC}")
    except:
        print(f"{Colors.FAIL}✗ npm not found - please install Node.js{Colors.ENDC}")
        return 1
    
    print()
    
    # Start servers
    backend_proc = start_backend()
    frontend_proc = start_frontend()
    
    if not backend_proc or not frontend_proc:
        print(f"\n{Colors.FAIL}Failed to start one or more servers!{Colors.ENDC}")
        if backend_proc:
            backend_proc.kill()
        if frontend_proc:
            frontend_proc.kill()
        return 1
    
    print(f"""
{Colors.OKGREEN}{Colors.BOLD}✓ All servers started successfully!{Colors.ENDC}

{Colors.BOLD}Access the application:{Colors.ENDC}
  • Frontend:  http://localhost:3000
  • Backend:   http://127.0.0.1:5000
  • Health:    http://127.0.0.1:5000/health

{Colors.WARNING}Press Ctrl+C to stop all servers...{Colors.ENDC}
    """)
    
    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print(f"{Colors.FAIL}[Backend]{Colors.ENDC} Backend server crashed!")
                break
            if frontend_proc.poll() is not None:
                print(f"{Colors.FAIL}[Frontend]{Colors.ENDC} Frontend dev server crashed!")
                break
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Shutting down servers...{Colors.ENDC}")
        backend_proc.terminate()
        frontend_proc.terminate()
        
        try:
            backend_proc.wait(timeout=5)
            frontend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"{Colors.WARNING}Force killing servers...{Colors.ENDC}")
            backend_proc.kill()
            frontend_proc.kill()
        
        print(f"{Colors.OKGREEN}✓ All servers stopped{Colors.ENDC}")
        return 0

if __name__ == "__main__":
    sys.exit(main())
