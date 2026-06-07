import os
import sys
import subprocess
import time
import webbrowser
import socket

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def run_command(cmd, cwd=None, env=None):
    print(f"Running: {' '.join(cmd)} in {cwd or '.'}")
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"Error executing {' '.join(cmd)}")
        sys.exit(result.returncode)

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    backend_dir = os.path.join(root_dir, "backend")

    print("="*50)
    print("🚀 Starting Publikater...")
    print("="*50)

    # 1. Build Frontend
    print("\n[1/3] Checking Frontend...")
    frontend_dist = os.path.join(frontend_dir, "dist")
    if not os.path.exists(frontend_dist) or "--rebuild" in sys.argv:
        print("Building the React frontend (this may take a minute)...")
        # Ensure npm is installed
        try:
            subprocess.run(["npm", "--version"], capture_output=True, check=True)
        except Exception:
            print("❌ Error: Node.js / npm is not installed. Please install Node.js from https://nodejs.org/")
            sys.exit(1)
            
        run_command(["npm", "install"], cwd=frontend_dir)
        run_command(["npm", "run", "build"], cwd=frontend_dir)
    else:
        print("Frontend already built. (Run with --rebuild to force a rebuild)")

    # 2. Check dependencies (handled by uv wrapper, but we just print status)
    print("\n[2/3] Preparing Backend Environment...")
    print("Dependencies are managed by uv.")

    # 3. Initialize Database
    print("\n[3/4] Initializing Database Schema...")
    env = os.environ.copy()
    env["PYTHONPATH"] = backend_dir
    run_command([sys.executable, "scripts/init_db.py"], cwd=backend_dir, env=env)

    # 4. Start Server
    print("\n[4/4] Starting Server...")
    port = 8001
    
    if is_port_in_use(port):
        print(f"⚠️ Port {port} is already in use. Assuming the server is already running.")
    else:
        # Start uvicorn as a subprocess
        env = os.environ.copy()
        env["PYTHONPATH"] = backend_dir
        
        # We assume this script is running INSIDE the uv environment already 
        # (because start.sh / start.bat uses `uv run launcher.py`)
        print("Starting Uvicorn...")
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", str(port)],
            cwd=backend_dir,
            env=env
        )

        # Wait for the server to start (First run can take 5+ mins to download PyTorch models)
        print("Waiting for server to initialize (This may take several minutes on first launch while AI models download)...")
        for _ in range(600):
            if is_port_in_use(port):
                break
            time.sleep(0.5)
        else:
            print("❌ Server failed to start in time.")
            server_process.terminate()
            sys.exit(1)

    print("\n✅ Publikater is ready!")
    url = f"http://localhost:{port}"
    print(f"Opening {url} in your browser...")
    webbrowser.open(url)
    
    try:
        # Keep the script running to keep the server alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down Publikater...")
        if 'server_process' in locals():
            server_process.terminate()
            server_process.wait()
        sys.exit(0)

if __name__ == "__main__":
    main()
