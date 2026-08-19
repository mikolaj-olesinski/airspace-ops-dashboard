"""Shared display formatting for turning live prediction dicts into LLM-readable text.

Used by both tools.py (chat) and briefing_agent.py (ops briefings) so a weather field
that's None -- a live source outage, see backend/predictions_service.py's fallback
handling -- reads as "n/a" instead of Python's literal "None" landing in an LLM prompt
(and, from there, potentially in what it writes back to a user).
"""


def fmt(value, unit: str = "") -> str:
    return "n/a" if value is None else f"{value}{unit}"


def weather_line(w: dict) -> str:
    return f"wind {fmt(w['wind_speed_10m'], ' km/h')}, temp {fmt(w['temperature_2m'], 'C')}, precip {fmt(w['precipitation'], ' mm')}"
