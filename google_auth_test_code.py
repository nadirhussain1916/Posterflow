import os
import sqlite3
from flask import Flask, json, redirect, url_for, session, request, jsonify, render_template_string
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
import pathlib
from openai import files
import datetime
import requests

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this in production

# Force OAuthlib to allow http:// for local dev
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_ID = "761667959165-08q7o0phqtb66uf7v2mk8sk7n6vuaet4.apps.googleusercontent.com"
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=[
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
        "https://www.googleapis.com/auth/drive.file",  # ✅ Add Drive scope
    ],
    redirect_uri="http://127.0.0.1:5000/callback"
)


# --- DB Setup ---
def init_db():
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

init_db()


@app.route("/")
def index():
    return '<a href="/login">Login with Google</a>'


@app.route("/login")
def login():
    authorization_url, state = flow.authorization_url(
        access_type="offline",             # ✅ Ask for refresh token
        include_granted_scopes="true",
        prompt="consent"                   # ✅ Force refresh token every time
    )
    session["state"] = state
    return redirect(authorization_url)



@app.route("/callback")
def callback():
    if "state" not in session:
        return "Session expired. Please try again.", 400

    flow.fetch_token(authorization_response=request.url)

    if not session["state"] == request.args["state"]:
        return "State mismatch. Please try again.", 400

    credentials = flow.credentials
    request_session = google.auth.transport.requests.Request()
    id_info = id_token.verify_oauth2_token(
        credentials._id_token, request_session, GOOGLE_CLIENT_ID
    )

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

    # ✅ Show upload form
    upload_form = """
    <h2>Welcome {{name}}!</h2>
    <img src="{{picture}}" width="100"><br>
    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file"><br><br>
        <button type="submit">Upload to Google Drive</button>
    </form>
    """
    return render_template_string(upload_form, name=id_info["name"], picture=id_info.get("picture"))

def get_valid_credentials(email):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token = row

    # Build credentials object
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=json.load(open("client_secret.json"))["web"]["client_secret"]
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


GDRIVE_FOLDER_ID = "1b068Va7q94iVtGEU-h-hfN_VQfBSTsDT"
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return "No file selected", 400
    file = request.files["file"]

    # Get latest user
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT email FROM users ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return "No authenticated user found", 401

    email = row[0]

    # ✅ Ensure token is valid or refresh it
    creds = get_valid_credentials(email)

    headers = {"Authorization": f"Bearer {creds.token}"}
    metadata = {
        "name": file.filename,
        "parents": [GDRIVE_FOLDER_ID]
    }
    files = {
        "data": ("metadata", str(metadata), "application/json; charset=UTF-8"),
        "file": file.stream
    }

    upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    response = requests.post(upload_url, headers=headers, files=files)

    if response.status_code == 200:
        file_id = response.json().get("id")
        return f"✅ File '{file.filename}' uploaded to Drive folder! (File ID: {file_id})"
    else:
        return f"❌ Upload failed: {response.text}", 400



@app.route("/users")
def list_users():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    rows = c.fetchall()
    conn.close()
    return jsonify(rows)


if __name__ == "__main__":
    app.run(debug=True)
