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
