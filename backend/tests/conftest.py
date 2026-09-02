"""Network-free test environment established before application modules are imported."""

import os

os.environ["LLM_MODE"] = "fixture"
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("LLM_BASE_URL", None)
os.environ.pop("LLM_MODEL", None)
