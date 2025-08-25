# PosterFlow - AI Image Generation with Google Drive Integration

Generate AI images using DALL-E and automatically upload them to Google Drive.

## Features

- 🎨 AI-powered image generation with OpenAI DALL-E
- 💭 ChatGPT prompt brainstorming
- 📱 Export to multiple print sizes (A3, A4, A5)
- ☁️ Google Drive integration for automatic uploads
- 🖼️ Streamlit web interface

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Setup Google Drive OAuth**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable Google Drive API
   - Create OAuth 2.0 credentials (Web application type)
   - Set authorized redirect URI to: `http://127.0.0.1:5001/callback`
   - Download the JSON file and save as `client_secret.json` in this directory
   - **Important**: Use `client_secret.json.template` as a reference for the file structure

3. **Set OpenAI API Key**
   - Get your API key from [OpenAI](https://platform.openai.com/api-keys)
   - Either:
     - Set environment variable: `set OPENAI_API_KEY=your_key_here`
     - Or enter it in the Streamlit sidebar

4. **Start the Application**
   ```bash
   python start_app.py
   ```
   
   This will start both:
   - OAuth Helper (port 5001) - handles Google authentication
   - Streamlit App (port 8501) - main application

5. **Open in Browser**
   - Streamlit App: http://localhost:8501
   - OAuth Helper: http://localhost:5001

## Usage

### Generate Images
1. Enter a concept, style, and keywords
2. Click "Generate prompts" to get AI-generated prompts
3. Select a prompt and generate images
4. Pick your favorite images

### Upload to Google Drive
1. Enable "Google Drive upload" in the sidebar
2. Click "Authenticate with Google" 
3. Complete the OAuth flow
4. Select images and click "Upload Selected to Drive"

### Export Print Files
1. Select images you want to export
2. Enter a folder name
3. Click "Export selected as ZIP"
4. Download the ZIP with A3, A4, A5 versions

## File Structure

```
├── app.py                 # Main Streamlit application
├── google_drive.py        # Google Drive integration
├── oauth_helper.py        # OAuth authentication handler
├── start_app.py          # Startup script
├── client_secret.json    # Google OAuth credentials (you need to add this)
├── requirements.txt      # Python dependencies
├── users.db             # SQLite database (created automatically)
└── README.md            # This file
```

## Troubleshooting

### OAuth Issues
- Make sure `client_secret.json` is in the correct directory
- Check that Google Drive API is enabled in Google Cloud Console
- Verify OAuth redirect URI is set to `http://127.0.0.1:5001/callback`

### Database Issues
- Delete `users.db` to reset authentication
- Use the "Clear All Users" button in the debug section

### Port Conflicts
- OAuth Helper uses port 5001
- Streamlit uses port 8501
- Make sure these ports are available

### Manual Token Entry
If OAuth flow doesn't work, you can manually enter tokens:
1. Go to OAuth Helper manually: http://localhost:5001/start_oauth
2. Complete authentication
3. Use developer tools to find access/refresh tokens
4. Enter them in the "Manual Token Entry" section

## Environment Variables

- `OPENAI_API_KEY` - Your OpenAI API key
- `OAUTHLIB_INSECURE_TRANSPORT=1` - Allows OAuth over HTTP (for local development)

## Google Drive Setup Details

1. **Google Cloud Console Setup**:
   - Project → APIs & Services → Library → Google Drive API → Enable
   - APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
   - Application type: Web application
   - Authorized redirect URIs: `http://127.0.0.1:5001/callback`

2. **Download Credentials**:
   - Download the JSON file
   - Rename to `client_secret.json`
   - Place in the same directory as `app.py`

## Development

### Running Components Separately

**OAuth Helper only:**
```bash
python oauth_helper.py
```

**Streamlit only:**
```bash
streamlit run app.py
```

### Debug Information
The app includes debug features:
- User database viewer
- OAuth status checker
- Manual token entry
- Clear users functionality

## Security Notes

- This is for local development only
- `client_secret.json` contains sensitive data - don't commit it
- The OAuth helper runs over HTTP (not HTTPS) for local development
- In production, use proper HTTPS and secure token storage

## License

This project is for educational and personal use.
