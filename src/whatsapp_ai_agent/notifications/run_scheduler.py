"""Console entry point for the Doceebot daily work-log reminder service.

Run by ``doceebot-reminder.service``::

    python -m whatsapp_ai_agent.notifications.run_scheduler

It builds the scheduler (from the same ``.env`` as the API) and blocks,
sleeping until the configured local fire time and broadcasting a rotated
reminder to every active conversation. When reminders are disabled the process
exits so systemd does not busy-loop.
"""

from __future__ import annotations

import logging
import sys

from whatsapp_ai_agent.notifications.reminder_scheduler import run_reminder_scheduler


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    scheduler = run_reminder_scheduler()
    if scheduler is None:
        # Disabled: exit cleanly so systemd does not restart in a tight loop.
        return 0
    scheduler.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
