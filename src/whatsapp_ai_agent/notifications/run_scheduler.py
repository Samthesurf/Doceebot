"""Console entry point for the Doceebot recurring jobs service.

Run by ``doceebot-reminder.service``::

    python -m whatsapp_ai_agent.notifications.run_scheduler

The process runs the weekday reminder and, when enabled, the Friday weekly DOCX
report job using the same ``.env`` as the API. It exits cleanly when no job is
enabled so systemd does not busy-loop.
"""

from __future__ import annotations

import logging
import sys

from whatsapp_ai_agent.notifications.reminder_scheduler import run_enabled_schedulers_forever


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_enabled_schedulers_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
