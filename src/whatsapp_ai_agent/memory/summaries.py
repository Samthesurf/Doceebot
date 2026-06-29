from dataclasses import dataclass


@dataclass(frozen=True)
class DailySummary:
    worker_name: str
    date: str
    summary: str
