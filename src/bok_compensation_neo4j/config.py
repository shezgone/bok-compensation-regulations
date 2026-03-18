import os
from dotenv import load_dotenv

# Load common env vars if present
load_dotenv()

# We will reuse the same environment variables or default to standard local Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
