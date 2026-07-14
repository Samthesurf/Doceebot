"""Daily work-log reminder copy for Doceebot.

Twenty rotating messages chosen to jolt the user out of autopilot and remind
them to log the day's work. They are deliberately varied in register (a
quiet question, a warm nudge, a bit of cheek, a reflective beat) so the daily
ping never dulls into background noise. None of them lead with the generic
"Hi, it's time to log your work." Instead each one is meant to make the
reader pause, then land on the realization that, oh right, the day actually
happened and it is worth writing down.
"""

from __future__ import annotations

REMINDER_MESSAGES: tuple[str, ...] = (
    "Wait. What did today actually cost you?",
    "The day's slipping out the back door. Wanna remember it, or write it down while it's warm?",
    "Quick gut check, what did you move today? Not what you planned. What you actually did.",
    "Future-you is about to open this log and judge past-you. Give them something good to read.",
    "If someone asked what you did from sunup to now, could you prove it? Let's make it real.",
    "Okay real talk, the memory is already starting to blur. Catch it.",
    "Your wins were quiet today. That's exactly why they need a paper trail.",
    "The clock hit 5:30 and the day is asking for its receipt. What are you logging?",
    "Don't let today become a blurry 'I was busy.' Show me the receipts.",
    "Somewhere between the first task and the last, you did something worth keeping. Find it.",
    "Honestly? Tomorrow-you will thank you for the two minutes this takes right now.",
    "The work happened. The proof hasn't. Close that gap.",
    "Picture it's Friday and you're staring at an empty log. Not today. Log it.",
    "You showed up today. The least we can do is remember how.",
    "A day unlogged is a day the world can argue never happened. Disagree, in writing.",
    "The group chat will forget. Your log won't. What's the story?",
    "Breathe. Then tell me, what actually went down today?",
    "This is your 5:30 nudge from the universe, via me. What'd you build?",
    "Most people let the day evaporate. You're not most people. Document it.",
    "Before you close the laptop, one line. Just one. What did today mean?",
)


def reminder_count() -> int:
    """Return how many reminder messages are configured."""

    return len(REMINDER_MESSAGES)


def reminder_at(index: int) -> str:
    """Return the message at ``index``, wrapping so rotation never runs out."""

    if not REMINDER_MESSAGES:
        raise ValueError("No reminder messages are configured")
    return REMINDER_MESSAGES[index % len(REMINDER_MESSAGES)]
