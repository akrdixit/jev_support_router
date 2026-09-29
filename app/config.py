import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
JEV_MODEL = os.getenv("JEV_MODEL", "jev-latest")
JEV_TIMEOUT_SECONDS = float(os.getenv("JEV_TIMEOUT_SECONDS", "15"))

# Max tickets classified concurrently in a batch request
BATCH_CONCURRENCY = int(os.getenv("BATCH_CONCURRENCY", "8"))

# Routing policy thresholds (probabilities 0-1)
TEAM_CONFIDENCE_MIN = float(os.getenv("TEAM_CONFIDENCE_MIN", "0.6"))
SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "0.8"))
ESCALATION_THRESHOLD = float(os.getenv("ESCALATION_THRESHOLD", "0.7"))
