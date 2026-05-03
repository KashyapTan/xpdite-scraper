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
    PYTHONUNBUFFERED=1

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy the current directory contents into the container at $HOME/app setting the owner to the user
COPY --chown=user . $HOME/app

# Install standard Python requirements using pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Install browser-based tiers for Docker (commented out in requirements.txt for Vercel)
RUN pip install --no-cache-dir browserforge>=1.2.4 camoufox[geoip]>=0.4.11 nodriver>=0.48.1 playwright>=1.58.0

# Install Playwright OS dependencies as root
USER root
RUN /home/user/.local/bin/playwright install-deps chromium

# Install Playwright browsers and Camoufox binaries as user
USER user
RUN playwright install chromium
RUN camoufox fetch

# Expose the port for FastAPI/Uvicorn
EXPOSE 7860

# Command to run the FastAPI application with Uvicorn
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
