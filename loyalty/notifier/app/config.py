import os

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
MIN_DELAY_MS = int(os.getenv("MIN_DELAY_MS", "200"))
MAX_DELAY_MS = int(os.getenv("MAX_DELAY_MS", "1500"))
UNSUBSCRIBED = {c.strip() for c in os.getenv("UNSUBSCRIBED", "").split(",") if c.strip()}
