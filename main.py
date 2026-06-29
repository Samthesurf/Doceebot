import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whatsapp_ai_agent.main import app, run  # noqa: E402,F401

if __name__ == "__main__":
    run()
