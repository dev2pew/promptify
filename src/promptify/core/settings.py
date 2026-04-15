"""
Global settings and environment variable configurations defining limits and locale settings.
"""

import os
from dotenv import load_dotenv

load_dotenv()

MAX_FILE_SIZE: int = int(os.getenv("PROMPTIFY_MAX_FILE_SIZE", 5 * 1024 * 1024))
MAX_CONCURRENT_READS: int = int(os.getenv("PROMPTIFY_MAX_CONCURRENT_READS", 100))
LOCALE: str = os.getenv("PROMPTIFY_LOCALE", "en")
