"""Network-free test environment established before application modules are imported."""

import os

os.environ["LLM_MODE"] = "fixture"
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("LLM_BASE_URL", None)
os.environ.pop("LLM_MODEL", None)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("REG_BRIDGE_DATABASE_URL", None)
os.environ.pop("VERCEL", None)
