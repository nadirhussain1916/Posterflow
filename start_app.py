"""
Setup script to run both OAuth helper and Streamlit app
"""
import subprocess
import sys
import time
import os
from pathlib import Path

def main():
    print("🚀 Starting PosterFlow with Google Drive Integration")
    print("=" * 50)
    
    # Get the current directory
    current_dir = Path(__file__).parent
    
    # Python executable path
    python_exe = current_dir / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = "python"  # Fallback to system python
    
    print(f"Using Python: {python_exe}")
    
    try:
        # Start OAuth helper in background
        print("1. Starting OAuth Helper on port 5001...")
        oauth_process = subprocess.Popen([
            str(python_exe), "oauth_helper.py"
        ], cwd=current_dir)
        
        # Give OAuth helper time to start
        time.sleep(2)
        
        # Start Streamlit app
        print("2. Starting Streamlit app on port 8501...")
        streamlit_process = subprocess.Popen([
            str(python_exe), "-m", "streamlit", "run", "app.py"
        ], cwd=current_dir)
        
        print("\n✅ Both services are starting!")
        print("📋 URLs:")
        print("   - Streamlit App: http://localhost:8501")
        print("   - OAuth Helper: http://localhost:5001")
        print("\n💡 Usage:")
        print("   1. Open the Streamlit app in your browser")
        print("   2. Generate some images")
        print("   3. Enable Google Drive upload")
        print("   4. Click 'Authenticate with Google'")
        print("   5. Complete the authentication")
        print("   6. Upload your images!")
        print("\n⚠️  Keep this terminal open - closing it will stop both services")
        print("   Press Ctrl+C to stop both services")
        
        # Wait for both processes
        try:
            oauth_process.wait()
            streamlit_process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping services...")
            oauth_process.terminate()
            streamlit_process.terminate()
            print("✅ Services stopped.")
            
    except Exception as e:
        print(f"❌ Error starting services: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
