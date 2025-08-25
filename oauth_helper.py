"""
OAuth Helper for Streamlit Google Drive Integration

This is a simple Flask server that handles OAuth callbacks for the Streamlit app.
Run this alongside your Streamlit app to handle authentication.

Usage:
1. Run this script: python oauth_helper.py
2. Run your Streamlit app: streamlit run app.py
3. Use the authentication flow in Streamlit

The Flask server will handle the OAuth callback and save tokens to the database.
"""

import os
import sqlite3
import json
import pathlib
import logging
from flask import Flask, request, redirect, jsonify
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
app.secret_key = "oauth_helper_secret"

# Force OAuthlib to allow http:// for local dev
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_ID = "761667959165-08q7o0phqtb66uf7v2mk8sk7n6vuaet4.apps.googleusercontent.com"

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
        logging.error("client_secret.json file not found")
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
            redirect_uri="http://127.0.0.1:5001/callback"  # OAuth helper port
        )
        return flow
    except Exception as e:
        logging.error(f"Error creating OAuth flow: {e}")
        return None

@app.route("/")
def index():
    return """
    <h2>OAuth Helper for Streamlit Google Drive</h2>
    <p>This service handles OAuth callbacks for your Streamlit app.</p>
    <p>Status: Running on port 5001</p>
    <p><a href="/start_oauth">Start OAuth Flow</a></p>
    """

@app.route("/start_oauth")
def start_oauth():
    """Start OAuth flow"""
    flow = get_oauth_flow()
    if not flow:
        return "Error: Could not create OAuth flow", 500
    
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    
    # Store state in a simple way (in production, use proper session management)
    with open("oauth_state.txt", "w") as f:
        f.write(state)
    
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    """Handle OAuth callback"""
    try:
        # Read stored state
        try:
            with open("oauth_state.txt", "r") as f:
                stored_state = f.read().strip()
        except FileNotFoundError:
            stored_state = None
        
        # Get state from request
        request_state = request.args.get("state")
        
        if stored_state and stored_state != request_state:
            return "State mismatch error", 400
        
        # Exchange code for tokens
        flow = get_oauth_flow()
        if not flow:
            return "Error creating OAuth flow", 500
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Get user info
        user_info_url = f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={credentials.token}"
        response = requests.get(user_info_url)
        if response.status_code != 200:
            return f"Failed to get user info: {response.text}", 400
        
        id_info = response.json()
        
        # Save to database
        init_db()
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
        
        # Clean up state file
        try:
            os.remove("oauth_state.txt")
        except FileNotFoundError:
            pass
        
        logging.info(f"OAuth successful for user: {id_info['email']}")
        
        return f"""
        <html>
        <head>
            <title>Authentication Successful</title>
            <meta http-equiv="refresh" content="3;url=http://localhost:8501">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
                .container {{ background: rgba(255, 255, 255, 0.1); padding: 30px; border-radius: 15px; box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37); backdrop-filter: blur(4px); border: 1px solid rgba(255, 255, 255, 0.18); }}
                .success {{ color: #4CAF50; font-size: 24px; margin-bottom: 20px; }}
                .countdown {{ color: #f0f0f0; font-size: 16px; margin: 20px 0; }}
                .spinner {{ border: 4px solid rgba(255, 255, 255, 0.3); border-top: 4px solid #4CAF50; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }}
                @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                .link {{ color: #90CAF9; text-decoration: none; }}
                .link:hover {{ color: #BBDEFB; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✅ Authentication Successful!</div>
                <h3>Welcome, <strong>{id_info.get('name', id_info['email'])}</strong>!</h3>
                <p>Your Google Drive access has been configured successfully.</p>
                <p>You can now save your generated images directly to Google Drive!</p>
                
                <div class="spinner"></div>
                <p class="countdown">Redirecting to Streamlit app in <span id="countdown">3</span> seconds...</p>
                <p><a href="http://localhost:8501" class="link">Click here if not redirected automatically</a></p>
                <button onclick="window.close()" style="margin-top: 10px; padding: 8px 16px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer;">Close This Window</button>
            </div>
            
            <script>
                var timeLeft = 3;
                var timer = setInterval(function() {{
                    timeLeft--;
                    document.getElementById('countdown').textContent = timeLeft;
                    if (timeLeft <= 0) {{
                        clearInterval(timer);
                        window.location.href = 'http://localhost:8501';
                    }}
                }}, 1000);
            </script>
        </body>
        </html>
        """
        
    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return f"Authentication failed: {str(e)}", 500

@app.route("/status")
def status():
    """Check authentication status"""
    try:
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT email, name FROM users ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                "authenticated": True,
                "email": row[0],
                "name": row[1]
            })
        else:
            return jsonify({"authenticated": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clear_users")
def clear_users():
    """Clear all users (for testing)"""
    try:
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        return "All users cleared successfully"
    except Exception as e:
        return f"Error clearing users: {e}", 500

if __name__ == "__main__":
    init_db()
    print("🚀 OAuth Helper starting on http://127.0.0.1:5001")
    print("📋 Available endpoints:")
    print("   - http://127.0.0.1:5001/ (home)")
    print("   - http://127.0.0.1:5001/start_oauth (start authentication)")
    print("   - http://127.0.0.1:5001/status (check auth status)")
    print("   - http://127.0.0.1:5001/clear_users (clear all users)")
    print("")
    print("💡 Instructions:")
    print("   1. Keep this server running")
    print("   2. Run your Streamlit app: streamlit run app.py")
    print("   3. Use the authentication button in Streamlit")
    print("")
    app.run(host="127.0.0.1", port=5001, debug=True)
