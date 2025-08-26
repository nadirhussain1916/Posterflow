import os
import sqlite3
import json
import pathlib
import logging
from io import BytesIO
from typing import Optional, Dict, List
import streamlit as st
import requests
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load Google OAuth configuration from client_secret.json and environment
def load_google_config():
    """Load Google OAuth configuration from client_secret.json and environment variables"""
    client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")
    
    # Default values
    config = {
        "client_id": None,
        "client_secret": None,
        "folder_id": os.getenv("GDRIVE_FOLDER_ID"),
        "oauth_host": os.getenv("OAUTH_HELPER_HOST", "127.0.0.1"),
        "oauth_port": int(os.getenv("OAUTH_HELPER_PORT", "5001")),
        "streamlit_host": os.getenv("STREAMLIT_HOST", "127.0.0.1"),
        "streamlit_port": int(os.getenv("STREAMLIT_PORT", "8501")),
        "database_path": os.getenv("DATABASE_PATH", "users.db")
    }
    
    # Load from client_secret.json if available
    if os.path.exists(client_secrets_file):
        try:
            with open(client_secrets_file) as f:
                client_secrets = json.load(f)
                if "web" in client_secrets:
                    config["client_id"] = client_secrets["web"].get("client_id")
                    config["client_secret"] = client_secrets["web"].get("client_secret")
                elif "installed" in client_secrets:
                    config["client_id"] = client_secrets["installed"].get("client_id")
                    config["client_secret"] = client_secrets["installed"].get("client_secret")
        except Exception as e:
            logging.error(f"Error loading client_secret.json: {e}")
    
    # Override with environment variables if set
    if os.getenv("GOOGLE_CLIENT_ID"):
        config["client_id"] = os.getenv("GOOGLE_CLIENT_ID")
    if os.getenv("GOOGLE_CLIENT_SECRET"):
        config["client_secret"] = os.getenv("GOOGLE_CLIENT_SECRET")
    
    return config

# Load configuration
GOOGLE_CONFIG = load_google_config()
GOOGLE_CLIENT_ID = GOOGLE_CONFIG["client_id"]
GOOGLE_CLIENT_SECRET = GOOGLE_CONFIG["client_secret"]
GDRIVE_FOLDER_ID = GOOGLE_CONFIG["folder_id"]
OAUTH_HELPER_HOST = GOOGLE_CONFIG["oauth_host"]
OAUTH_HELPER_PORT = GOOGLE_CONFIG["oauth_port"]
STREAMLIT_HOST = GOOGLE_CONFIG["streamlit_host"]
STREAMLIT_PORT = GOOGLE_CONFIG["streamlit_port"]
DATABASE_PATH = GOOGLE_CONFIG["database_path"]

# Force OAuthlib to allow http:// for local dev
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

def init_db():
    """Initialize SQLite database for storing user credentials"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            name TEXT,
            picture TEXT,
            access_token TEXT,
            refresh_token TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_oauth_flow():
    """Create Google OAuth flow"""
    client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")
    
    if not os.path.exists(client_secrets_file):
        st.error("client_secret.json file not found. Please ensure it's in the same directory as this app.")
        return None
    
    if not GOOGLE_CLIENT_ID:
        st.error("Google Client ID not found. Please check your client_secret.json file or environment variables.")
        return None
    
    try:
        flow = Flow.from_client_secrets_file(
            client_secrets_file=client_secrets_file,
            scopes=[
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/userinfo.email",
                "openid",
                "https://www.googleapis.com/auth/drive.file",
            ],
            redirect_uri=f"http://{STREAMLIT_HOST}:{STREAMLIT_PORT}/callback"
        )
        return flow
    except Exception as e:
        st.error(f"Error creating OAuth flow: {e}")
        return None

def get_valid_credentials(email: str) -> Optional[Credentials]:
    """Get valid credentials for a user, refreshing if necessary"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token = row

    try:
        # Build credentials object
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET
        )

        # Refresh if needed
        if creds.expired and creds.refresh_token:
            request_session = google.auth.transport.requests.Request()
            creds.refresh(request_session)

            # Save new token
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("UPDATE users SET access_token=? WHERE email=?", (creds.token, email))
            conn.commit()
            conn.close()

        return creds
    except Exception as e:
        logging.error(f"Error getting credentials: {e}")
        return None

def upload_image_to_drive(image_bytes: bytes, filename: str, user_email: str) -> Dict:
    """Upload image bytes to Google Drive"""
    try:
        if not GDRIVE_FOLDER_ID:
            return {"success": False, "error": "Google Drive folder ID not configured. Please set GDRIVE_FOLDER_ID in .env file."}
        
        creds = get_valid_credentials(user_email)
        if not creds:
            return {"success": False, "error": "No valid credentials found"}

        headers = {"Authorization": f"Bearer {creds.token}"}
        metadata = {
            "name": filename,
            "parents": [GDRIVE_FOLDER_ID]
        }
        
        # Create file-like object from bytes
        files = {
            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (filename, BytesIO(image_bytes), "image/png")
        }

        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
        response = requests.post(upload_url, headers=headers, files=files)

        if response.status_code == 200:
            file_id = response.json().get("id")
            return {
                "success": True, 
                "file_id": file_id,
                "message": f"File '{filename}' uploaded successfully!"
            }
        else:
            return {
                "success": False, 
                "error": f"Upload failed: {response.text}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_authenticated_user() -> Optional[str]:
    """Get the email of the authenticated user"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def debug_show_users():
    """Debug function to show all users in database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, email, name, access_token IS NOT NULL as has_token, refresh_token IS NOT NULL as has_refresh FROM users")
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logging.error(f"Error getting users: {e}")
        return []

def check_oauth_helper_status() -> bool:
    """Check if OAuth helper is running"""
    try:
        response = requests.get(f"http://{OAUTH_HELPER_HOST}:{OAUTH_HELPER_PORT}/status", timeout=2)
        return response.status_code == 200
    except:
        return False

def save_manual_tokens(email: str, access_token: str, refresh_token: Optional[str] = None):
    """Save manually entered tokens to database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (email, name, picture, access_token, refresh_token) VALUES (?, ?, ?, ?, ?)
        """, (email, email.split('@')[0], "", access_token, refresh_token))
        c.execute("""
            UPDATE users SET access_token=?, refresh_token=? WHERE email=?
        """, (access_token, refresh_token, email))
        conn.commit()
        conn.close()
        logging.info(f"Tokens saved for user: {email}")
    except Exception as e:
        logging.error(f"Error saving tokens: {e}")

def display_gdrive_upload_ui(images: List[Dict]):
    """Display Google Drive upload UI in Streamlit"""
    st.subheader("🔗 Upload to Google Drive")
    
    # Initialize database
    init_db()
    
    # Check configuration
    if not GDRIVE_FOLDER_ID:
        st.error("❌ Google Drive folder ID not configured. Please set GDRIVE_FOLDER_ID in your .env file.")
        return
    
    if not GOOGLE_CLIENT_ID:
        st.error("❌ Google Client ID not found. Please check your client_secret.json file.")
        return
    
    # Check if user is authenticated
    user_email = get_authenticated_user()
    
    if not user_email:
        st.info("You need to authenticate with Google to upload images to Drive.")
        
        # Check if OAuth helper is running
        oauth_helper_status = check_oauth_helper_status()
        
        if oauth_helper_status:
            st.success("✅ OAuth Helper is running")
            st.write("**Recommended: Use OAuth Helper (easier)**")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔐 Authenticate with Google", type="primary"):
                    st.markdown("Click the link below to authenticate:")
                    st.markdown(f"[🔗 **Authenticate with Google**](http://{OAUTH_HELPER_HOST}:{OAUTH_HELPER_PORT}/start_oauth)")
                    st.info("After authentication, refresh this page to see your status.")
            
            with col2:
                if st.button("🔄 Check Status"):
                    st.rerun()
        else:
            st.warning("⚠️ OAuth Helper is not running")
            st.write("**Option 1: Start OAuth Helper**")
            st.code("python oauth_helper.py", language="bash")
            st.write("Then refresh this page and use the authentication button above.")
            
            st.write("**Option 2: Manual Token Entry**")
        
        # Manual token entry section (always available)
        with st.expander("🔧 Manual Token Entry (Advanced)"):
            st.write("If you have Google OAuth tokens, you can enter them manually:")
            manual_email = st.text_input("Email", key="manual_email")
            manual_access_token = st.text_input("Access Token", type="password", key="manual_access")
            manual_refresh_token = st.text_input("Refresh Token (optional)", type="password", key="manual_refresh")
            
            if st.button("💾 Save Tokens") and manual_email and manual_access_token:
                save_manual_tokens(manual_email, manual_access_token, manual_refresh_token)
                st.success("✅ Tokens saved! Please refresh the page.")
                st.rerun()
    else:
        st.success(f"✅ Authenticated as: {user_email}")
        
        # Show debug info
        with st.expander("🔍 Debug Info"):
            users = debug_show_users()
            if users:
                st.write("Users in database:")
                for user in users:
                    st.write(f"- ID: {user[0]}, Email: {user[1]}, Name: {user[2]}, Has Token: {user[3]}, Has Refresh: {user[4]}")
            else:
                st.write("No users found in database")
            
            # Show configuration
            st.write("Configuration:")
            st.write(f"- Database: {DATABASE_PATH}")
            st.write(f"- OAuth Helper: {OAUTH_HELPER_HOST}:{OAUTH_HELPER_PORT}")
            st.write(f"- Google Drive Folder ID: {GDRIVE_FOLDER_ID}")
            st.write(f"- Google Client ID: {GOOGLE_CLIENT_ID[:20]}..." if GOOGLE_CLIENT_ID else "- Google Client ID: Not configured")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Logout"):
                # Clear user from database
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE email=?", (user_email,))
                conn.commit()
                conn.close()
                st.rerun()
        
        with col2:
            if st.button("🧹 Clear All Users"):
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM users")
                conn.commit()
                conn.close()
                st.success("All users cleared!")
                st.rerun()
        
        # Upload section
        st.write("Select images to upload:")
        upload_selected = []
        
        for i, item in enumerate(images):
            if st.checkbox(f"Upload {item['name']}", key=f"upload_{i}"):
                upload_selected.append(i)
        
        if upload_selected and st.button("📤 Upload Selected to Drive"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, idx in enumerate(upload_selected):
                item = images[idx]
                status_text.text(f"Uploading {item['name']}...")
                progress_bar.progress((i) / len(upload_selected))
                
                result = upload_image_to_drive(item["bytes"], item["name"], user_email)
                
                if result["success"]:
                    st.success(result["message"])
                else:
                    st.error(f"Failed to upload {item['name']}: {result['error']}")
            
            progress_bar.progress(1.0)
            status_text.text("Upload complete!")
            
            # Clean up progress indicators after a moment
            import time
            time.sleep(2)
            progress_bar.empty()
            status_text.empty()
