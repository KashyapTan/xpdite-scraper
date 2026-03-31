FROM python:3.11-slim

# Install system dependencies required for headless browsers
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libfontconfig1 \
    xvfb \
    libxrender1 \
    libxext6 \
    libxi6 \
    libxtst6 \
    vim \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=7860 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy the current directory contents into the container at $HOME/app setting the owner to the user
COPY --chown=user . $HOME/app

# Install standard Python requirements using pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (if Playwright is used)
USER root
RUN playwright install-deps chromium
USER user
RUN playwright install chromium

# Expose the port Streamlit will run on
EXPOSE 7860

# Command to run the Streamlit application
CMD ["streamlit", "run", "web_ui.py"]
