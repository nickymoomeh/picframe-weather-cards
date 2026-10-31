from datetime import timedelta

CODES = {
    "sunny": 0,
    "partly-cloudy": 2,
    "overcast": 3,
    "rain": 61,
    "heavy-rain": 65,
    "thunderstorm": 95,
    "snow": 73,
    "fog": 45,
    "clear-night": 0,
    "cloudy-night": 63,
}


def sample(now, kind):
    t = int(now.timestamp())
    start = t - t % 3600
    c = dict(
        time=t,
        temperature_2m=1 if kind == "snow" else 14,
        apparent_temperature=-2 if kind == "snow" else 12,
        relative_humidity_2m=78,
        precipitation=0.4 if "rain" in kind else 0,
        wind_speed_10m=12,
        wind_gusts_10m=21,
        pressure_msl=1016,
        weather_code=CODES[kind],
        is_day=int("night" not in kind),
    )
    hourly = {"time": [start + i * 3600 for i in range(72)]}
    for k in ("temperature_2m", "weather_code", "is_day"):
        hourly[k] = [c[k]] * 72
    hourly["is_day"] = [
        int(7 <= __import__("datetime").datetime.fromtimestamp(v, now.tzinfo).hour < 17)
        for v in hourly["time"]
    ]
    hourly["precipitation_probability"] = [65 if c["precipitation"] else 10] * 72
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ds = [int((midnight + timedelta(days=i)).timestamp()) for i in range(3)]
    daily = dict(
        time=ds,
        temperature_2m_max=[16] * 3,
        temperature_2m_min=[9] * 3,
        sunrise=[v + 7 * 3600 for v in ds],
        sunset=[v + 17 * 3600 for v in ds],
    )
    return dict(current=c, hourly=hourly, daily=daily)
