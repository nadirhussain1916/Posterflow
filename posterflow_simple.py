
import os
import io
import base64
import datetime as dt
from typing import List, Dict, Tuple

import streamlit as st
import logging
from dotenv import load_dotenv
from PIL import Image

# ========== CONFIG ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
load_dotenv()
st.set_page_config(page_title="PosterFlow (Simple)", page_icon="🎨", layout="wide")

# Helper: convert bytes to downloadable link
def download_bytes(data: bytes, filename: str, mime: str = "application/octet-stream"):
    logging.info(f"Preparing download link for {filename}")
    b64 = base64.b64encode(data).decode()
    href = f'<a download="{filename}" href="data:{mime};base64,{b64}">⬇ Download {filename}</a>'
    st.markdown(href, unsafe_allow_html=True)

# ---------- Print helpers ----------
PRINT_SIZES = {
    "A3": (3508, 4961),  # 297 x 420 mm at 300DPI
    "A4": (2480, 3508),  # 210 x 297 mm
    "A5": (1748, 2480),  # 148 x 210 mm
}

def square_to_portrait(img: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    logging.info(f"Resizing image to portrait size {target_size}")
    target_w, target_h = target_size
    img = img.convert("RGB")
    # Fit to width
    scale = target_w / img.width
    new_w = target_w
    new_h = int(img.height * scale)
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    if new_h > target_h:
        # Fit to height if overflow
        scale = target_h / img.height
        new_h = target_h
        new_w = int(img.width * scale)
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    # Pad with white
    canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
    x = (target_w - resized.width) // 2
    y = (target_h - resized.height) // 2
    canvas.paste(resized, (x, y))
    return canvas

def make_print_variants(png_bytes: bytes) -> Dict[str, bytes]:
    logging.info("Generating print variants (A3/A4/A5)")
    from io import BytesIO
    img = Image.open(BytesIO(png_bytes))
    outputs = {}
    for size_name, px in PRINT_SIZES.items():
        portrait = square_to_portrait(img, px)
        buf = BytesIO()
        portrait.save(buf, format="JPEG", quality=95, subsampling=0)
        outputs[size_name] = buf.getvalue()
    return outputs

# ---------- Sidebar Secrets ----------
st.sidebar.header("🔐 Keys (use Streamlit Secrets in Cloud)")
logging.info("Sidebar loaded. Awaiting API key and options.")
st.sidebar.caption("You can also set these under App -> Settings -> Secrets on Streamlit Cloud.")
OPENAI_API_KEY = st.sidebar.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))

st.sidebar.markdown("---")
st.sidebar.subheader("Optional Cloud & Shop (advanced)")
GDRIVE_ENABLED = st.sidebar.checkbox("Enable Google Drive upload", value=False)
TTS_ENABLED = st.sidebar.checkbox("Enable TikTok Shop upload", value=False)

if GDRIVE_ENABLED:
    st.sidebar.caption("Put Google OAuth JSON in Streamlit Secrets as 'gdrive_client_secrets'")
if TTS_ENABLED:
    TTS_BASE_URL = st.sidebar.text_input("TikTok Base URL", value=os.getenv("TTS_BASE_URL","https://open-api.tiktokglobalshop.com"))
    TTS_APP_KEY   = st.sidebar.text_input("App Key", value=os.getenv("TTS_APP_KEY",""))
    TTS_APP_SECRET= st.sidebar.text_input("App Secret", type="password", value=os.getenv("TTS_APP_SECRET",""))
    TTS_ACCESS    = st.sidebar.text_input("Access Token", type="password", value=os.getenv("TTS_ACCESS_TOKEN",""))
    TTS_SHOP_ID   = st.sidebar.text_input("Shop ID", value=os.getenv("TTS_SHOP_ID",""))

st.title("🎨 PosterFlow — Simple")
logging.info("App started. Title and flow description displayed.")

st.write("**Flow:** Brainstorm → Generate → Pick best → Export A3/A4/A5 (and optionally upload).")

# ---------- 1) Brainstorm ----------
st.header("1) Brainstorm with ChatGPT")
logging.info("Step 1: Brainstorm UI loaded.")
col1, col2, col3 = st.columns(3)
with col1:
    concept = st.text_input("Concept", "funny, sarcastic office motivation")
with col2:
    style = st.text_input("Style", "minimalist, bold typography, high-contrast")
with col3:
    keywords = st.text_input("Keywords", "desk setup, hustle, coffee, productivity")

n_prompts = st.slider("How many prompt options?", 1, 5, 3)
prompt_btn = st.button("✨ Generate prompts")

if prompt_btn:
    logging.info("Prompt generation button clicked.")
    if not OPENAI_API_KEY:
        logging.warning("No OpenAI API key provided.")
        st.error("Please add your OpenAI API key in the sidebar.")
    else:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            system = ("You generate concise, vivid image prompts for AI artwork. "
                      "Keep each under 100 words. Include subject, mood, composition, colour palette, and style cues. "
                      "Avoid naming living artists.")
            user = f"Concept: {concept}\nStyle: {style}\nKeywords: {keywords}\nCreate {n_prompts} different prompts."
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                temperature=0.9
            )
            if resp and resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                text = resp.choices[0].message.content.strip()
                prompts = [p.strip("-• ").strip() for p in text.split("\n") if p.strip()]
                if len(prompts) < n_prompts:
                    prompts = [p.strip() for p in text.split("\n\n") if p.strip()]
                st.session_state["prompts"] = prompts[:n_prompts]
                st.success("Prompts generated.")
                logging.info(f"Prompts generated: {prompts[:n_prompts]}")
            else:
                st.error("No response from OpenAI.")
                logging.error("No response from OpenAI.")
        except Exception as e:
            st.error(f"OpenAI error: {e}")

if "prompts" in st.session_state:
    st.subheader("Prompt options")
    for i, p in enumerate(st.session_state["prompts"], 1):
        st.markdown(f"**{i}.** {p}")
    chosen_idx = st.number_input("Pick a prompt", 1, len(st.session_state["prompts"]), 1)
    chosen_prompt = st.session_state["prompts"][chosen_idx-1]
else:
    logging.info("Generating prompts with OpenAI ChatGPT.")
    logging.info("Prompts available. Displaying options.")
    chosen_prompt = None

# ---------- 2) Generate images ----------
st.header("2) Generate with DALL·E")
logging.info("Step 2: Image generation UI loaded.")
num_images = st.slider("How many images?", 1, 6, 4)
gen_btn = st.button("🖼️ Generate images")

if gen_btn:
    logging.info("Image generation button clicked.")
    if not OPENAI_API_KEY:
        logging.warning("No OpenAI API key provided for image generation.")
        st.error("Please add your OpenAI API key in the sidebar.")
    elif not chosen_prompt:
        logging.warning("No prompt chosen for image generation.")
        st.error("Generate prompts and pick one first.")
    else:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            logging.info(f"Requesting {num_images} images from OpenAI DALL·E with prompt: {chosen_prompt}")
            resp = client.images.generate(
                model="dall-e-3",
                prompt=chosen_prompt,
                n=num_images,
                size="1024x1024",
                response_format="b64_json"
            )
            images = []
            if resp and resp.data:
                for i, d in enumerate(resp.data):
                    if d and hasattr(d, 'b64_json') and d.b64_json:
                        raw = base64.b64decode(d.b64_json)
                        images.append({"name": f"gen_{i+1}.png", "bytes": raw})
            st.session_state["images"] = images
            logging.info(f"Generated {len(images)} image(s) and stored in session state.")
            st.success(f"Generated {len(images)} image(s).")
        except Exception as e:
            logging.error(f"OpenAI image error: {e}")
            st.error(f"OpenAI image error: {e}")

# ---------- 3) Pick best ----------
selected = []
if "images" in st.session_state:
    logging.info("Images available. Displaying selection UI.")
    st.subheader("Pick your favourite(s)")
    cols = st.columns(3)
    for i, item in enumerate(st.session_state["images"]):
        c = cols[i % 3]
        c.image(item["bytes"], caption=item["name"])
        if c.checkbox(f"Select {item['name']}", key=f"sel_{i}"):
            selected.append(i)

# ---------- 4) Export A3/A4/A5 ----------
st.header("4) Export print files (300 DPI)")
logging.info("Step 4: Export UI loaded.")
folder_name = st.text_input("Export folder name", dt.datetime.now().strftime("Run-%Y%m%d-%H%M"))
export_btn = st.button("📦 Export selected as ZIP")

if export_btn:
    logging.info("Export button clicked.")
    if not selected:
        logging.warning("No images selected for export.")
        st.error("Select at least one image.")
    else:
        logging.info(f"Exporting {len(selected)} selected images as ZIP.")
        import zipfile
        from io import BytesIO
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx in selected:
                item = st.session_state["images"][idx]
                variants = make_print_variants(item["bytes"])
                for sz, data in variants.items():
                    zf.writestr(f"{folder_name}/{item['name'].replace('.png','')}_{sz}.jpg", data)
                zf.writestr(f"{folder_name}/{item['name']}", item["bytes"])
        zip_bytes = zip_buf.getvalue()
        download_bytes(zip_bytes, f"{folder_name}.zip", "application/zip")
        st.success("ZIP ready. Click to download.")
        logging.info("ZIP file created and download link provided.")

st.caption("Optional advanced: enable Google Drive/TikTok in the sidebar and extend this app later. This single-file version focuses on easy creation and export.")
logging.info("App ready. Awaiting further user actions.")
