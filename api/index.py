# Vercel serverless entry point
# Re-exports the FastAPI app from main.py for Vercel's api/ convention

import sys
from pathlib import Path

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
