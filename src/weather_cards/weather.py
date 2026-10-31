import math

CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow",
    95: "Thunderstorm",
    96: "Thunder with hail",
    99: "Thunder with hail",
}
CURRENT = {
    "temperature_2m": (-100, 65),
    "apparent_temperature": (-120, 80),
    "relative_humidity_2m": (0, 100),
    "precipitation": (0, 500),
    "wind_speed_10m": (0, 300),
    "wind_gusts_10m": (0, 400),
    "pressure_msl": (800, 1100),
    "weather_code": (0, 99),
    "is_day": (0, 1),
}
HOURLY = {k: CURRENT[k] for k in ("temperature_2m", "weather_code", "is_day")} | {
    "precipitation_probability": (0, 100)
}
DAILY = {"temperature_2m_max": (-100, 65), "temperature_2m_min": (-100, 65)}


def number(v, lo, hi):
    if (
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not lo <= v <= hi
    ):
        raise ValueError("Invalid numeric weather value")
    return v


def validate(data):
    try:
        c = data["current"]
        number(c["time"], 0, 4102444800)
        for k, r in CURRENT.items():
            number(c[k], *r)
        for name, fields in (("hourly", HOURLY), ("daily", DAILY)):
            block = data[name]
            ts = block["time"]
            if not isinstance(ts, list) or not ts or len(ts) > 400:
                raise ValueError("Forecast length")
            for t in ts:
                number(t, 0, 4102444800)
            if any(a >= b for a, b in zip(ts, ts[1:])):
                raise ValueError("Unordered timestamps")
            for k, r in fields.items():
                if len(block[k]) != len(ts):
                    raise ValueError("Array mismatch")
                for v in block[k]:
                    number(v, *r)
        for name in ("sunrise", "sunset"):
            if len(data["daily"][name]) != len(data["daily"]["time"]):
                raise ValueError("Solar array mismatch")
            for t in data["daily"][name]:
                number(t, 0, 4102444800)
        for block in (c, data["hourly"]):
            codes = (
                block["weather_code"]
                if isinstance(block["weather_code"], list)
                else [block["weather_code"]]
            )
            days = (
                block["is_day"]
                if isinstance(block["is_day"], list)
                else [block["is_day"]]
            )
            if any(v not in CODES for v in codes) or any(v not in (0, 1) for v in days):
                raise ValueError("Unknown weather code/day flag")
        if not data["hourly"]["time"][0] <= c["time"] <= data["hourly"]["time"][-1]:
            raise ValueError("Current outside forecast")
        d = data["daily"]
        for i in range(len(d["time"])):
            if (
                d["temperature_2m_min"][i] > d["temperature_2m_max"][i]
                or d["sunrise"][i] >= d["sunset"][i]
            ):
                raise ValueError("Inconsistent daily values")
    except (KeyError, TypeError, IndexError, OverflowError) as e:
        raise ValueError("Incomplete weather response") from e
    return data


def theme(code, day):
    if not day:
        return "clear-night" if code in (0, 1) else "cloudy-night"
    if code >= 95:
        return "thunderstorm"
    if code in (56, 57, 66, 67, 71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (65, 82):
        return "heavy-rain"
    if code in (51, 53, 55, 61, 63, 80, 81):
        return "rain"
    if code in (45, 48):
        return "fog"
    return {0: "sunny", 1: "sunny", 2: "partly-cloudy", 3: "overcast"}.get(
        code, "overcast"
    )


def periods(data, now):
    h = data["hourly"]
    out = []
    last = 0
    for i, t in enumerate(h["time"]):
        if t > now.timestamp() and t >= last:
            out.append({k: v[i] for k, v in h.items()})
            last = t + 3 * 3600
            if len(out) == 4:
                break
    return out


def layout(cfg, data):
    if cfg.layout != "automatic":
        return cfg.layout
    c = data["current"]
    return (
        "detailed"
        if c["precipitation"] > 0
        or c["wind_gusts_10m"] >= 25
        or c["weather_code"] >= 45
        else "minimal"
    )
