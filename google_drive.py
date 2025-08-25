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

# Google OAuth configuration
GOOGLE_CLIENT_ID = "761667959165-08q7o0phqtb66uf7v2mk8sk7n6vuaet4.apps.googleusercontent.com"
GDRIVE_FOLDER_ID = "1b068Va7q94iVtGEU-h-hfN_VQfBSTsDT"

# Force OAuthlib to allow http:// for local dev
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

def init_db():
    """Initialize SQLite database for storing user credentials"""
    conn = sqlite3.connect("users.db")
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
    
    try:
        flow = Flow.from_client_secrets_file(
            client_secrets_file=client_secrets_file,
            scopes=[
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/userinfo.email",
                "openid",
                "https://www.googleapis.com/auth/drive.file",
            ],
            redirect_uri="http://127.0.0.1:8501/callback"  # Streamlit default port
        )
        return flow
    except Exception as e:
        st.error(f"Error creating OAuth flow: {e}")
        return None

def get_valid_credentials(email: str) -> Optional[Credentials]:
    """Get valid credentials for a user, refreshing if necessary"""
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token = row

    try:
        # Load client secret for refresh
        client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")
        with open(client_secrets_file) as f:
            client_secret = json.load(f)["web"]["client_secret"]

        # Build credentials object
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=client_secret
        )

        # Refresh if needed
        if creds.expired and creds.refresh_token:
            request_session = google.auth.transport.requests.Request()
            creds.refresh(request_session)

            # Save new token
            conn = sqlite3.connect("users.db")
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
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT email FROM users ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def debug_show_users():
    """Debug function to show all users in database"""
    try:
        conn = sqlite3.connect("users.db")
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
        response = requests.get("http://127.0.0.1:5001/status", timeout=2)
        return response.status_code == 200
    except:
        return False

def save_manual_tokens(email: str, access_token: str, refresh_token: Optional[str] = None):
    """Save manually entered tokens to database"""
    try:
        conn = sqlite3.connect("users.db")
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

def handle_streamlit_oauth_callback() -> bool:
    """Handle OAuth callback from Streamlit query parameters"""
    try:
        query_params = st.query_params
        code = query_params.get("code")
        state = query_params.get("state")
        
        if not code or not state:
            return False
        
        # Check if state matches (if we stored it)
        stored_state = st.session_state.get("oauth_state")
        if stored_state and stored_state != state:
            logging.error("OAuth state mismatch")
            return False
        
        # Exchange code for tokens
        flow = get_oauth_flow()
        if not flow:
            return False
        
        # Construct the full callback URL
        callback_url = f"http://127.0.0.1:8501/callback?code={code}&state={state}"
        flow.fetch_token(authorization_response=callback_url)
        
        credentials = flow.credentials
        
        # Get user info
        user_info_url = f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={credentials.token}"
        response = requests.get(user_info_url)
        if response.status_code == 200:
            id_info = response.json()
        else:
            logging.error("Failed to get user info")
            return False
        
        # Save to database
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (email, name, picture, access_token, refresh_token) VALUES (?, ?, ?, ?, ?)
        """, (
            id_info["email"],
            id_info.get("name", id_info["email"].split('@')[0]),
            id_info.get("picture", ""),
            credentials.token,
            getattr(credentials, "refresh_token", None)
        ))
        c.execute("""
            UPDATE users SET access_token=?, refresh_token=?, name=?, picture=? WHERE email=?
        """, (
            credentials.token,
            getattr(credentials, "refresh_token", None),
            id_info.get("name", id_info["email"].split('@')[0]),
            id_info.get("picture", ""),
            id_info["email"]
        ))
        conn.commit()
        conn.close()
        
        logging.info(f"OAuth callback successful for user: {id_info['email']}")
        return True
        
    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return False

def handle_manual_oauth_callback(callback_url: str, expected_state: Optional[str] = None) -> bool:
    """Handle OAuth callback from manually pasted URL"""
    try:
        # Parse the URL to extract code and state
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(callback_url)
        query_params = parse_qs(parsed.query)
        
        code = query_params.get("code", [None])[0]
        state = query_params.get("state", [None])[0]
        
        if not code:
            logging.error("No authorization code in callback URL")
            return False
        
        # Exchange code for tokens
        flow = get_oauth_flow()
        if not flow:
            return False
        
        flow.fetch_token(authorization_response=callback_url)
        credentials = flow.credentials
        
        # Get user info
        user_info_url = f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={credentials.token}"
        response = requests.get(user_info_url)
        if response.status_code == 200:
            id_info = response.json()
        else:
            logging.error("Failed to get user info")
            return False
        
        # Save to database
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (email, name, picture, access_token, refresh_token) VALUES (?, ?, ?, ?, ?)
        """, (
            id_info["email"],
            id_info.get("name", id_info["email"].split('@')[0]),
            id_info.get("picture", ""),
            credentials.token,
            getattr(credentials, "refresh_token", None)
        ))
        c.execute("""
            UPDATE users SET access_token=?, refresh_token=?, name=?, picture=? WHERE email=?
        """, (
            credentials.token,
            getattr(credentials, "refresh_token", None),
            id_info.get("name", id_info["email"].split('@')[0]),
            id_info.get("picture", ""),
            id_info["email"]
        ))
        conn.commit()
        conn.close()
        
        logging.info(f"Manual OAuth callback successful for user: {id_info['email']}")
        return True
        
    except Exception as e:
        logging.error(f"Manual OAuth callback error: {e}")
        return False

def display_gdrive_upload_ui(images: List[Dict]):
    """Display Google Drive upload UI in Streamlit"""
    st.subheader("🔗 Upload to Google Drive")
    
    # Initialize database
    init_db()
    
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
                    st.markdown("[🔗 **Authenticate with Google**](http://127.0.0.1:5001/start_oauth)")
                    st.info("After authentication, refresh this page to see your status.")
            
            with col2:
                if st.button("� Check Status"):
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
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Logout"):
                # Clear user from database
                conn = sqlite3.connect("users.db")
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE email=?", (user_email,))
                conn.commit()
                conn.close()
                st.rerun()
        
        with col2:
            if st.button("🧹 Clear All Users"):
                conn = sqlite3.connect("users.db")
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

def handle_oauth_callback(authorization_response: str, state: str):
    """Handle OAuth callback (for manual implementation if needed)"""
    try:
        flow = get_oauth_flow()
        if not flow:
            return False
        
        flow.fetch_token(authorization_response=authorization_response)
        
        credentials = flow.credentials
        
        # Get user info using the access token
        user_info_url = f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={credentials.token}"
        response = requests.get(user_info_url)
        if response.status_code == 200:
            id_info = response.json()
        else:
            logging.error("Failed to get user info")
            return False

        # Save user + tokens
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (email, name, picture, access_token, refresh_token) VALUES (?, ?, ?, ?, ?)
        """, (
            id_info["email"],
            id_info.get("name"),
            id_info.get("picture"),
            credentials.token,
            getattr(credentials, "refresh_token", None)
        ))
        c.execute("""
            UPDATE users SET access_token=?, refresh_token=? WHERE email=?
        """, (
            credentials.token,
            getattr(credentials, "refresh_token", None),
            id_info["email"]
        ))
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return False
