import os

DATABASE_URL = os.environ["DATABASE_URL"]
RABBITMQ_URL = os.environ["RABBITMQ_URL"]

OPERATIONS_EXCHANGE = "loyalty"
OPERATIONS_QUEUE = "operations"
OPERATIONS_KEY = "operation"
PUBLISH_TIMEOUT = float(os.getenv("PUBLISH_TIMEOUT", "5"))
