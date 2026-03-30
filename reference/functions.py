# functions.py
from uagents import Model
import requests

class WeatherRequest(Model):
    location : str

class WeatherResponse(Model):
    weather : str

def get_weather(location: str):
    """Return current weather for a location string (e.g., 'Paris, France')."""
    if not location or not location.strip():
        raise ValueError("location is required")

    # 1) Geocode
    geo_params = {"name": location, "count": 1, "language": "en", "format": "json"}
    gr = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params=geo_params,
        timeout=60,
    )
    gr.raise_for_status()
    g = gr.json()
    if not g.get("results"):
        raise RuntimeError(f"No geocoding match for: {location}")

    r0 = g["results"][0]
    latitude = r0["latitude"]
    longitude = r0["longitude"]
    timezone = r0.get("timezone") or "auto"
    display = ", ".join([v for v in [r0.get("name"), r0.get("admin1"), r0.get("country")] if v])

    # 2) Current weather
    wx_params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m,wind_direction_10m,is_day,precipitation"
        ),
    }
    wr = requests.get("https://api.open-meteo.com/v1/forecast", params=wx_params, timeout=60)
    wr.raise_for_status()
    data = wr.json()

    current = data.get("current") or data.get("current_weather") or {}
    temp = current.get("temperature_2m")
    app = current.get("apparent_temperature")
    wind = current.get("wind_speed_10m")
    rh = current.get("relative_humidity_2m")

    parts = [f"Weather for {display}"]
    if temp is not None:
        parts.append(f"temp {temp}°C")
    if app is not None:
        parts.append(f"feels like {app}°C")
    if rh is not None:
        parts.append(f"RH {rh}%")
    if wind is not None:
        parts.append(f"wind {wind} km/h")

    return {"weather": ", ".join(parts)}
