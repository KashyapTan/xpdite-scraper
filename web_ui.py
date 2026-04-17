import streamlit as st
import asyncio
import sys
from pathlib import Path
import base64

sys.path.append(str(Path(__file__).parent))
from scrape.scraper import scrape


def get_base64_of_bin_file(bin_file):
    with open(bin_file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


logo_path = Path(__file__).parent / "assets" / "logo.svg"
logo_base64 = ""
if logo_path.exists():
    logo_base64 = get_base64_of_bin_file(str(logo_path))

st.set_page_config(page_title="XpditeS Web Scraper", page_icon="🕸️", layout="wide")

custom_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600&display=swap');
    
    .stApp {
        background-color: #000000 !important;
        font-family: 'Montserrat', sans-serif !important;
    }
    
    h1, h2, h3, h4, h5, h6, label, p, .stMarkdown p {
        color: #eeeeee !important;
        font-family: 'Montserrat', sans-serif !important;
    }

    div[data-testid="column"] {
        background-color: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        padding: 20px !important;
        margin-top: 10px !important;
    }
    
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
        background-color: rgba(0, 0, 0, 0.2) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: white !important;
        border-radius: 6px !important;
        padding: 8px !important;
    }
    
    .stTextInput input:focus, .stSelectbox div[data-baseweb="select"]:hover, .stTextArea textarea:focus {
        border-color: #3b82f6 !important;
        background-color: rgba(0, 0, 0, 0.3) !important;
        box-shadow: none !important;
        color: white !important;
    }

    .stButton > button {
        background-color: #3b82f6 !important;
        color: white !important;
        border: none !important;
        padding: 6px 14px !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        font-family: 'Montserrat', sans-serif !important;
        transition: background-color 0.2s !important;
        margin-top: 15px !important;
    }
    
    .stButton > button:hover, .stButton > button:focus, .stButton > button:active {
        background-color: #2563eb !important;
        color: white !important;
        box-shadow: none !important;
        border: none !important;
    }
    
    .custom-header {
        display: flex;
        align-items: center;
        gap: 15px;
        margin-bottom: 20px;
        padding-bottom: 15px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .custom-header img {
        height: 60px;
        border-radius: 8px;
    }
    .custom-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 600;
        color: #fff !important;
    }
    
    .stRadio div[role="radiogroup"] label {
        background: transparent !important;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

if logo_base64:
    st.markdown(
        f"""
        <div class="custom-header">
            <img src="data:image/svg+xml;base64,{logo_base64}" alt="Xpdite Logo">  
            <h1>XpditeS Scraper</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.title("🕸️ XpditeS Scraper")

left_col, right_col = st.columns([1, 2.5])

with left_col:
    st.markdown("### Settings")
    url_input = st.text_input("Target URL", placeholder="https://example.com")

    st.markdown("#### Options")
    mode_choice = st.radio(
        "Extraction Mode",
        options=["precision", "full"],
        format_func=lambda x: (
            "Precision (Main article content only)"
            if x == "precision"
            else "Full (Raw Markdown of entire page)"
        ),
        index=0,
    )

    tier_choice = st.selectbox(
        "Scraping Tier",
        options=["Auto", "1", "2", "3"],
        format_func=lambda x: (
            "Auto (Fallback through tiers)" if x == "Auto" else f"Tier {x}"
        ),
    )

    start_button = st.button("Start Scraping", type="primary", use_container_width=True)

    st.markdown("---")
    st.markdown(
        "**Note:** This UI runs the scraper in real-time. When scraping completes, the output will appear directly on the right side of the screen."
    )

with right_col:
    st.markdown("### Scraped Content")
    output_placeholder = st.empty()

    if start_button:
        if not url_input.strip() or not url_input.startswith("http"):
            output_placeholder.error(
                "Please enter a valid URL starting with http:// or https://"
            )
        else:
            with output_placeholder.container():
                with st.spinner(f"Scraping {url_input}..."):
                    try:
                        import scrape.scraper as scraper
                        import time

                        force_tier_val = (
                            None if tier_choice == "Auto" else int(tier_choice)
                        )

                        start_time = time.time()
                        result = asyncio.run(
                            scraper.scrape(
                                url_input,
                                force_tier=force_tier_val,
                                mode=mode_choice,
                            )
                        )
                        elapsed_time = time.time() - start_time

                        if result:
                            label, content = result
                            st.success(f"Successfully scraped using tier: **{label}**")
                            st.text_area(
                                f"Raw Output ({len(content):,} characters | {elapsed_time:.2f} seconds)",
                                value=content,
                                height=700,
                            )
                        else:
                            st.error(
                                "Failed — all scraping tiers exhausted. Could not extract content."
                            )
                    except Exception as e:
                        st.error(f"An error occurred during execution: {str(e)}")
    else:
        output_placeholder.info(
            "Enter a URL on the left and click 'Start Scraping' to see the textual results here."
        )
