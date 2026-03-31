import streamlit as st
import asyncio
import sys
from pathlib import Path

# Ensure the scrape module is in the Python path
sys.path.append(str(Path(__file__).parent))
from scrape.scraper import scrape

# Configure the page layout to use the full width
st.set_page_config(page_title="XpditeS Web Scraper", page_icon="🕷️", layout="wide")

st.title("🕷️ XpditeS Web Scraper")

# Create a 2-column layout (Left narrow for inputs, Right wide for output text)
left_col, right_col = st.columns([1, 2.5])

with left_col:
    st.markdown("### Settings")
    url_input = st.text_input("Target URL", placeholder="https://example.com")
    
    st.markdown("#### Options")
    mode_choice = st.radio(
        "Extraction Mode",
        options=["precision", "full"],
        format_func=lambda x: "Precision (Main article content only)" if x == "precision" else "Full (Raw Markdown of entire page)",
        index=0
    )
    
    tier_choice = st.selectbox(
        "Scraping Tier",
        options=["Auto", "1", "2", "3"],
        format_func=lambda x: "Auto (Fallback through tiers)" if x == "Auto" else f"Tier {x}"
    )

    start_button = st.button("Start Scraping", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.markdown("**Note:** This UI runs the scraper in real-time. When scraping completes, the output will appear directly on the right side of the screen instead of being saved to a file.")

with right_col:
    st.markdown("### Scraped Content")
    output_placeholder = st.empty()
    
    if start_button:
        if not url_input.strip() or not url_input.startswith("http"):
            output_placeholder.error("Please enter a valid URL starting with http:// or https://")
        else:
            with output_placeholder.container():
                with st.spinner(f"Scraping {url_input}... (this might take a few moments depending on the tier)"):
                    try:
                        import scrape.scraper as scraper
                        import time
                        
                        # Set the global extraction mode
                        scraper._EXTRACT_MODE = mode_choice
                        
                        # Determine the force_tier argument
                        force_tier_val = None if tier_choice == "Auto" else int(tier_choice)

                        # Track start time
                        start_time = time.time()
                        
                        # Call the async scrape function
                        result = asyncio.run(scraper.scrape(url_input, force_tier=force_tier_val))
                        
                        # Calculate elapsed time
                        elapsed_time = time.time() - start_time
                        
                        if result:
                            label, content = result
                            st.success(f"Successfully scraped using tier: **{label}**")
                            # Display the text in a large text area window
                            st.text_area(f"Raw Output ({len(content):,} characters | {elapsed_time:.2f} seconds)", value=content, height=700)
                        else:
                            st.error("Failed — all scraping tiers exhausted. Could not extract content.")
                            
                    except Exception as e:
                        st.error(f"An error occurred during execution: {str(e)}")
    else:
        output_placeholder.info("Enter a URL on the left and click 'Start Scraping' to see the textual results here.")
