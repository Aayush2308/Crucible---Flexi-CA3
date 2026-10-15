"""Root Pytest Configuration.

Ensures that the repository root is automatically added to sys.path
for deterministic module discovery across all environments.
"""

import sys
from pathlib import Path

# Add repository root to python search path
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
