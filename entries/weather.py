import json
import urllib.parse
import urllib.request

from django.conf import settings

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


WEATHER_ANIMATIONS = {
    0: "sunny",
    1: "sunny",
    2: "cloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rain",
    53: "rain",
    55: "rain",
    56: "rain",
    57: "rain",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "rain",
    67: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "storm",
    96: "storm",
    99: "storm",
}


def get_current_weather():
    """Fetch a short "72°F, Partly cloudy" style summary, or None on any failure.

    Best-effort external call on a page-render path: any network, API, or
    schema problem should degrade to no weather shown rather than break
    the check-in page.
    """
    params = urllib.parse.urlencode(
        {
            "latitude": settings.WEATHER_LATITUDE,
            "longitude": settings.WEATHER_LONGITUDE,
            "current": "temperature_2m,weather_code",
            "temperature_unit": "fahrenheit",
            "timezone": settings.WEATHER_TIMEZONE,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.load(response)
        current = data["current"]
        temperature = round(current["temperature_2m"])
        description = WEATHER_CODES.get(current["weather_code"], "Unknown conditions")
        return f"{temperature}°F, {description}"
    except Exception:
        return None


def get_tomorrow_forecast():
    """Fetch a short "81°F / 64°F, Slight rain" style forecast for tomorrow, or None on failure.

    Best-effort external call on a page-render path, same contract as
    get_current_weather(): never raise, just return None so the evening
    check-in still renders without a forecast.
    """
    params = urllib.parse.urlencode(
        {
            "latitude": settings.WEATHER_LATITUDE,
            "longitude": settings.WEATHER_LONGITUDE,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "temperature_unit": "fahrenheit",
            "timezone": settings.WEATHER_TIMEZONE,
            "forecast_days": 2,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.load(response)
        daily = data["daily"]
        high = round(daily["temperature_2m_max"][1])
        low = round(daily["temperature_2m_min"][1])
        description = WEATHER_CODES.get(daily["weather_code"][1], "Unknown conditions")
        return f"{high}°F / {low}°F, {description}"
    except Exception:
        return None


def weather_animation_for_summary(summary):
    """Map a cached "72°F, Partly cloudy" summary back to an animation category.

    entries.Entry only stores the formatted summary string, not the raw
    weather_code, so this matches the description half against WEATHER_CODES
    to recover it. Returns None if summary is empty or doesn't match any
    known description (e.g. old cached data from before a code was added).
    """
    if not summary or ", " not in summary:
        return None
    description = summary.split(", ", 1)[1]
    for code, text in WEATHER_CODES.items():
        if text == description:
            return WEATHER_ANIMATIONS.get(code)
    return None
