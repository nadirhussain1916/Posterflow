# PosterFlow (Simple) — Streamlit, single file

This is the **easy version**: one Streamlit file that
1) brainstorms prompts (ChatGPT),
2) generates multiple images (DALL·E),
3) exports **A3/A4/A5** 300‑DPI print files in a ZIP.

### Run locally (Windows/Mac)
1. Install Python 3.10+
2. `pip install -r requirements.txt`
3. Set your OpenAI key:
   - EITHER: `set OPENAI_API_KEY=sk-...` (Windows) or `export OPENAI_API_KEY=sk-...` (Mac/Linux)
   - OR put it in `.streamlit/secrets.toml`
4. `streamlit run posterflow_simple.py`

### Streamlit Community Cloud
1. Create a new app and upload these files.
2. In **App → Settings → Secrets**, paste:
```
OPENAI_API_KEY = "sk-..."
```
3. Deploy. Use the app in your browser.

### Notes
- This simple version skips Google Drive + TikTok upload to keep it easy and reliable. You can add those later.
- Export produces **A3/A4/A5** JPEGs (padded from 1024x1024 square) plus the original PNG, in a single ZIP download.