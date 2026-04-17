import streamlit as st
import asyncio
import sys
from pathlib import Path
import base64

# Ensure the scrape module is in the Python path
sys.path.append(str(Path(__file__).parent))
from scrape.scraper import scrape


# ── INJECT CUSTOM CSS ───────────────────────────────────────
# We use the styling references provided from the user's CSS (SettingsSkills.css)
def get_base64_of_bin_file(bin_file):
    with open(bin_file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


# Try to load the logo
logo_path = Path(__file__).parent / "assets" / "logo.svg"
logo_base64 = ""
if logo_path.exists():
    logo_base64 = get_base64_of_bin_file(str(logo_path))

st.set_page_config(page_title="XpditeS Web Scraper", page_icon="🕸️", layout="wide")

custom_css = """
<style>
    /* Global Base mimicking the provided CSS background and text */
    .stApp {
        background-color: #0f1115; /* Dark background from UI context */
        color: #eee;
        font-family: 'Montserrat', sans-serif;
    }
    
    /* Headers */
    h1, h2, h3, h4, .stMarkdown p {
        color: #fff !important;
    }
    
    /* Input Elements mimicking .editor-group inputs */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: white !important;
        border-radius: 6px !important;
    }
    
    .stTextInput input:focus, .stSelectbox div[data-baseweb="select"]:hover, .stTextArea textarea:focus {
        border-color: #3b82f6 !important;
        background-color: rgba(0, 0, 0, 0.3) !important;
    }
    
    /* Main Button mimicking .create-skill-btn & .save-btn */
    .stButton > button {
        background-color: #3b82f6 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        transition: background-color 0.2s !important;
        font-family: 'Montserrat', sans-serif !important;
    }
    
    .stButton > button:hover {
        background-color: #2563eb !important;
    }
    
    /* Header layout with Logo */
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
    }

    /* Cards styling mirroring .skill-card */
    .css-1y4p8pa { /* Streamlit container override */
        background-color: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        padding: 16px !important;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ── RENDER HEADER WITH LOGO ─────────────────────────────────
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

# Create a 2-column layout (Left narrow for inputs, Right wide for output text)
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
        "**Note:** This UI runs the scraper in real-time. When scraping completes, the output will appear directly on the right side of the screen instead of being saved to a file."
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
                with st.spinner(
                    f"Scraping {url_input}... (this might take a few moments depending on the tier)"
                ):
                    try:
                        import scrape.scraper as scraper
                        import time

                        # Determine the force_tier argument
                        force_tier_val = (
                            None if tier_choice == "Auto" else int(tier_choice)
                        )

                        # Track start time
                        start_time = time.time()

                        # Call the async scrape function
                        result = asyncio.run(
                            scraper.scrape(
                                url_input,
                                force_tier=force_tier_val,
                                mode=mode_choice,
                            )
                        )

                        # Calculate elapsed time
                        elapsed_time = time.time() - start_time

                        if result:
                            label, content = result
                            st.success(f"Successfully scraped using tier: **{label}**")
                            # Display the text in a large text area window
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
