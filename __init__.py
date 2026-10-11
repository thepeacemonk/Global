# -*- coding: utf-8 -*-
# Global
#
# Author: PeaceMonk
# License: GNU AGPLv3
#
# This add-on displays the weather in the user's location by injecting
# HTML content into the deck browser's stats area using the Open-Meteo API.

import json
import requests
from datetime import datetime
import time
from urllib.parse import urlparse, parse_qs
import os
import base64
import colorsys

# Import gui_hooks for modern Anki versions
from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import showInfo, tooltip
import aqt.deckbrowser

from .settings import SettingsDialog
from . import bento_integration

# --- Configuration ---
ADDON_NAME = "Global"
ADDON_FOLDER = os.path.dirname(__file__)

try:
    CONFIG = mw.addonManager.getConfig(__name__)
    if not isinstance(CONFIG, dict):
        raise TypeError("Config is not a dictionary.")
except (TypeError, json.JSONDecodeError):
    CONFIG = {
        "view_mode": "mini",
        "units": "metric", # metric (celsius) or imperial (fahrenheit)
        "use_custom_url": False,
        "custom_api_url": "",
        "last_weather_data": None,
        "last_fetch_time": 0,
        "enable_gradients": True,
        "card_opacity": 1.0,
        "colors": {
            "light": {"card_background": "#FFFFFF"},
            "dark": {"card_background": "#2C2F33"},
        },
        "manual_widget_width": 211,
        "manual_widget_height": 300
    }
    mw.addonManager.writeConfig(__name__, CONFIG)

# Vertical was retired in favor of Mini and Pro. Normalize saved settings so
# existing users see one of the two available choices immediately.
if CONFIG.get("view_mode") == "vertical":
    CONFIG["view_mode"] = "mini"
    mw.addonManager.writeConfig(__name__, CONFIG)


# --- Weather Code Mapping (WMO) ---
# Maps WMO codes to a description and icon filenames.
WMO_MAP = {
    0: ("Clear sky", "sun.svg", "moon.svg"),
    1: ("Mainly clear", "sun-cloud.svg", "cloud.svg"),
    2: ("Partly cloudy", "cloud-sun-mix.svg", "cloud.svg"),
    3: ("Overcast", "cloud.svg", "cloud.svg"),
    45: ("Fog", "fog.svg", "fog.svg"),
    48: ("Depositing rime fog", "fog.svg", "fog.svg"),
    51: ("Light drizzle", "sun-rain.svg", "rain.svg"),
    53: ("Moderate drizzle", "sun-rain.svg", "rain.svg"),
    55: ("Dense drizzle", "rain.svg", "rain.svg"),
    56: ("Light freezing drizzle", "snow-light.svg", "snow-light.svg"),
    57: ("Dense freezing drizzle", "snow-light.svg", "snow-light.svg"),
    61: ("Slight rain", "sun-rain.svg", "rain.svg"),
    63: ("Moderate rain", "rain.svg", "rain.svg"),
    65: ("Heavy rain", "rain.svg", "rain.svg"),
    66: ("Light freezing rain", "snow-light.svg", "snow-light.svg"),
    67: ("Heavy freezing rain", "snow-light.svg", "snow-light.svg"),
    71: ("Slight snow fall", "snow-light.svg", "snow-light.svg"),
    73: ("Moderate snow fall", "snow.svg", "snow.svg"),
    75: ("Heavy snow fall", "snow.svg", "snow.svg"),
    77: ("Snow grains", "snow.svg", "snow.svg"),
    80: ("Slight rain showers", "rain.svg", "rain.svg"),
    81: ("Moderate rain showers", "rain.svg", "rain.svg"),
    82: ("Violent rain showers", "rain.svg", "rain.svg"),
    85: ("Slight snow showers", "snow-light.svg", "snow-light.svg"),
    86: ("Heavy snow showers", "snow.svg", "snow.svg"),
    95: ("Thunderstorm", "thunderstorm.svg", "thunderstorm.svg"),
    96: ("Thunderstorm with slight hail", "thunderstorm.svg", "thunderstorm.svg"),
    99: ("Thunderstorm with heavy hail", "thunderstorm.svg", "thunderstorm.svg"),
}

# --- Icon Loading (based on working example) ---

def load_svg_content(filename: str) -> str:
    """Loads raw SVG content from the 'icons' folder."""
    path = os.path.join(ADDON_FOLDER, "icons", filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    return ""

def load_image_as_base64(filename: str) -> str:
    """Loads a PNG image from the 'icons' folder and returns it as a Base64 data URI."""
    path = os.path.join(ADDON_FOLDER, "icons", filename)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                encoded_string = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{encoded_string}"
        except Exception:
            return ""
    return ""

# --- Data Fetching ---
def fetch_data_with_custom_url(custom_url):
    """Fetches weather and AQI data using a user-provided Open-Meteo URL."""
    try:
        # 1. Parse the custom URL to get user-defined parameters
        parsed_url = urlparse(custom_url)
        query_params = parse_qs(parsed_url.query)
        
        lat = query_params.get('latitude', [None])[0]
        lon = query_params.get('longitude', [None])[0]

        if not lat or not lon:
            tooltip("Custom URL must include 'latitude' and 'longitude'.")
            return None
        
        # 2. Build a new, robust set of parameters for the forecast API call.
        final_params = {k: v[0] for k, v in query_params.items()}

        # Add/overwrite the essential parameters to prevent parsing errors
        final_params["current"] = "temperature_2m,relative_humidity_2m,is_day,weather_code,apparent_temperature"
        final_params["hourly"] = "temperature_2m,weather_code"
        final_params["daily"] = "weather_code,temperature_2m_max,temperature_2m_min"
        
        if 'temperature_unit' not in final_params:
             final_params['temperature_unit'] = "fahrenheit" if CONFIG.get("units") == "imperial" else "celsius"

        # 3. Fetch forecast data
        forecast_url = "https://api.open-meteo.com/v1/forecast"
        forecast_res = requests.get(forecast_url, params=final_params, timeout=10)
        forecast_res.raise_for_status()
        forecast_data = forecast_res.json()

        # 4. Fetch Air Quality Data
        aqi_params = {"latitude": lat, "longitude": lon, "hourly": "us_aqi"}
        aqi_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        aqi_res = requests.get(aqi_url, params=aqi_params, timeout=10)
        aqi_res.raise_for_status()
        aqi_data = aqi_res.json()

        return {"city": "Custom Location", "forecast": forecast_data, "aqi": aqi_data}

    except requests.exceptions.RequestException as e:
        tooltip(f"Failed to fetch data with custom URL: {e}")
        return None
    except (KeyError, IndexError, TypeError):
        tooltip("Could not parse latitude/longitude from custom URL.")
        return None

def fetch_data_automatically():
    """Fetches weather and AQI data automatically using IP-based location."""
    try:
        # 1. Get location from IP
        loc_res = requests.get("http://ip-api.com/json/?fields=status,message,lat,lon,city", timeout=5)
        loc_res.raise_for_status()
        loc_data = loc_res.json()
        if loc_data.get("status") != "success":
            tooltip("Could not determine location.")
            return None
        lat, lon, city = loc_data['lat'], loc_data['lon'], loc_data['city']

        # 2. Get Weather Data
        temp_unit = "fahrenheit" if CONFIG.get("units") == "imperial" else "celsius"
        forecast_params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,is_day,weather_code,apparent_temperature",
            "hourly": "temperature_2m,weather_code", "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto", "temperature_unit": temp_unit,
        }
        forecast_url = "https://api.open-meteo.com/v1/forecast"
        forecast_res = requests.get(forecast_url, params=forecast_params, timeout=10)
        forecast_res.raise_for_status()
        forecast_data = forecast_res.json()

        # 3. Get Air Quality Data
        aqi_params = {"latitude": lat, "longitude": lon, "hourly": "us_aqi"}
        aqi_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        aqi_res = requests.get(aqi_url, params=aqi_params, timeout=10)
        aqi_res.raise_for_status()
        aqi_data = aqi_res.json()

        return {"city": city, "forecast": forecast_data, "aqi": aqi_data}

    except requests.exceptions.RequestException as e:
        tooltip(f"Couldn't fetch new weather: {e}. Showing cached data.")
        return CONFIG.get("last_weather_data")

def get_weather_data():
    """Main function to decide fetching method and handle caching."""
    last_fetch = CONFIG.get("last_fetch_time", 0)
    if (datetime.now().timestamp() - last_fetch) < (30 * 60) and CONFIG.get("last_weather_data"):
        return CONFIG["last_weather_data"]

    use_custom = CONFIG.get("use_custom_url", False)
    custom_url = CONFIG.get("custom_api_url", "").strip()

    weather_data = None
    if use_custom and custom_url:
        weather_data = fetch_data_with_custom_url(custom_url)
    
    if weather_data is None:
        weather_data = fetch_data_automatically()

    if weather_data:
        CONFIG["last_weather_data"] = weather_data
        CONFIG["last_fetch_time"] = datetime.now().timestamp()
        mw.addonManager.writeConfig(__name__, CONFIG)
    
    return weather_data


# --- Helper Functions ---
def get_aqi_text(aqi_val):
    """Converts a US AQI value to a user-friendly string with an icon."""
    if aqi_val is None:
        return f'Unknown <img src="{load_image_as_base64("unknown.png")}" class="aqi-icon">'
    
    icon_map = {
        "Good": "aqi-good.png", "Moderate": "aqi-moderate.png",
        "Unhealthy for Some": "aqi-unhealthy-some.png", "Unhealthy": "aqi-unhealthy.png",
        "Very Unhealthy": "aqi-very-unhealthy.png", "Hazardous": "aqi-hazardous.png"
    }
    
    text, icon_name = "Unknown", "unknown.png"
    if 0 <= aqi_val <= 50: text, icon_name = "Good", icon_map["Good"]
    elif 51 <= aqi_val <= 100: text, icon_name = "Moderate", icon_map["Moderate"]
    elif 101 <= aqi_val <= 150: text, icon_name = "Unhealthy for Some", icon_map["Unhealthy for Some"]
    elif 151 <= aqi_val <= 200: text, icon_name = "Unhealthy", icon_map["Unhealthy"]
    elif 201 <= aqi_val <= 300: text, icon_name = "Very Unhealthy", icon_map["Very Unhealthy"]
    else: text, icon_name = "Hazardous", icon_map["Hazardous"]
        
    return f'{text} <img src="{load_image_as_base64(icon_name)}" class="aqi-icon">'

def get_icon(code, is_day):
    """Returns the raw SVG content for the corresponding weather icon."""
    _, day_icon, night_icon = WMO_MAP.get(code, ("Unknown", "unknown.png", "unknown.png"))
    filename = day_icon if is_day else night_icon
    
    svg_content = load_svg_content(filename)
    
    img_class = "weather-icon"
    return f'<div class="{img_class}">{svg_content}</div>'

def get_gradient_class(code, is_day):
    """Determines the CSS gradient class based on weather code and time of day."""
    hour = datetime.now().hour
    class_name = ""
    if code in [0, 1]:
        if not is_day: class_name = "sunny-night"
        elif 5 <= hour < 12: class_name = "sunny-morning"
        elif 12 <= hour < 18: class_name = "sunny-afternoon"
        else: class_name = "evening"
    elif 51 <= code <= 67 or 80 <= code <= 82: class_name = "rainy"
    elif code in [56, 57, 66, 67] or 71 <= code <= 77 or 85 <= code <= 86: class_name = "snowy"
    elif code >= 95: class_name = "stormy"
    elif code in [2, 3, 45, 48]: class_name = "cloudy"
    
    if class_name:
        return f"global-gradient-{class_name}"
    return ""

def hex_to_rgba(hex_code, alpha):
    hex_code = hex_code.lstrip('#')
    r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"

# --- HTML & CSS Generation ---
def generate_css(is_dark, config=None):
    """Generates the complete CSS for the add-on."""
    if config is None:
        config = CONFIG
    opacity = config.get("card_opacity", 1.0)
    
    # Define colors
    if is_dark:
        text_color, text_muted = ("#ffffff", "#9e9e9e")
        icon_color = "#ffffff"
        card_bg_1_solid = hex_to_rgba("#3E4349", opacity)
        card_bg_2_solid = f"rgba(27, 27, 27, {opacity})"
    else:
        text_color, text_muted = ("#212121", "#616161")
        icon_color = "#212121"
        card_bg_1_solid = hex_to_rgba("#F0F3F4", opacity)
        card_bg_2_solid = hex_to_rgba("#FFFFFF", opacity)

    # Override card 1 background if gradients are disabled
    if not config.get("enable_gradients", True):
        theme_key = "dark" if is_dark else "light"
        default_flat = "#2C2F33" if is_dark else "#FFFFFF"
        flat_hex = config.get("colors", {}).get(theme_key, {}).get("card_background", default_flat)
        card_bg_1_solid = hex_to_rgba(flat_hex, opacity)

    # Define gradients (raw hex stops, so we can also derive a readable
    # on-gradient text/icon color per gradient below)
    gradient_stops = {
        "light": {
            "sunny-morning":   ['#f5e3e6', '#fde4a0', '#c8e7e9'],
            "sunny-afternoon": ['#d4e7ff', '#a8caff', '#89acff'],
            "evening":         ['#ff7e5f', '#feb47b', '#ffcc70'],
            "rainy":           ['#a7b3be', '#c0c8d1', '#b4c2d1'],
            "cloudy":          ['#C9DEF4', '#F5CCD4', '#B8A4C9'],
            "snowy":           ['#e7eff9', '#f8f1f8', '#ffffff'],
            "stormy":          ['#536976', '#292E49', '#536976'],
            "sunny-night":     ['#667eea', '#764ba2', '#6B8DD6'],
        },
        "dark": {
            "sunny-morning":   ['#4F4343', '#7D5E5E', '#9C8383'],
            "sunny-afternoon": ['#1e3c72', '#2a5298', '#4a6da7'],
            "evening":         ['#EF709B', '#F5BD82', '#FA9372'],
            "rainy":           ['#37474f', '#263238', '#4f5a63'],
            "cloudy":          ['#455A64', '#607D8B', '#546E7A'],
            "snowy":           ['#485461', '#28313b', '#485461'],
            "stormy":          ['#1F1C2C', '#3A355A', '#1F1C2C'],
            "sunny-night":     ['#0f2027', '#203a43', '#2c5364'],
        }
    }
    theme = "dark" if is_dark else "light"

    def _hex_to_rgb01(hex_code):
        hex_code = hex_code.lstrip('#')
        r, g, b = tuple(int(hex_code[i:i + 2], 16) for i in (0, 2, 4))
        return r / 255.0, g / 255.0, b / 255.0

    def _gradient_ink_colors(stops):
        """Derive a text/icon color that keeps the gradient's own hue (so it
        visually matches that gradient) instead of falling back to plain
        black/white, while still pushing lightness/saturation far enough
        for the text to stay readable against the gradient."""
        rgbs = [_hex_to_rgb01(c) for c in stops]
        r = sum(c[0] for c in rgbs) / len(rgbs)
        g = sum(c[1] for c in rgbs) / len(rgbs)
        b = sum(c[2] for c in rgbs) / len(rgbs)
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if luminance > 0.55:
            # Light gradient: a deep, saturated shade of its own hue reads
            # as "colored ink", not just black.
            text_l, text_s = 0.22, min(1.0, s + 0.35)
            icon_l, icon_s = 0.28, min(1.0, s + 0.3)
        else:
            # Dark gradient: a pale, softly-tinted shade of its own hue
            # instead of plain white.
            text_l, text_s = 0.92, min(1.0, s * 0.6 + 0.2)
            icon_l, icon_s = 0.88, min(1.0, s * 0.6 + 0.25)
        tr, tg, tb = colorsys.hls_to_rgb(h, text_l, text_s)
        ir, ig, ib = colorsys.hls_to_rgb(h, icon_l, icon_s)
        text_hex = f"#{int(tr * 255):02x}{int(tg * 255):02x}{int(tb * 255):02x}"
        icon_hex = f"#{int(ir * 255):02x}{int(ig * 255):02x}{int(ib * 255):02x}"
        muted_rgba = f"rgba({int(tr * 255)}, {int(tg * 255)}, {int(tb * 255)}, 0.75)"
        return text_hex, muted_rgba, icon_hex

    gradient_rules = ""
    for name, stops in gradient_stops[theme].items():
        gradient_css = f"linear-gradient(135deg, {', '.join(hex_to_rgba(c, opacity) for c in stops)})"

        # Pick text/icon colors that read clearly against this specific
        # gradient's own colors, instead of inheriting the theme's fixed
        # text color (which can be unreadable on e.g. the dark "stormy"
        # gradient in light mode, or vice versa) — and tinted with the
        # gradient's own hue rather than plain black/white.
        on_text, on_muted, on_icon = _gradient_ink_colors(stops)

        # The base "color" rule above is scoped to
        # `#global-container #global-weather-wrapper` (two ID selectors), which
        # outranks a plain `.global-card-1.global-gradient-*` override on
        # specificity even with !important on both sides — so this one needs
        # the same #global-weather-wrapper prefix to actually win.
        gradient_rules += f"""
        #global-container .global-card-1.global-gradient-{name} {{ background: {gradient_css} !important; }}
        #global-container #global-weather-wrapper .global-card-1.global-gradient-{name} {{ color: {on_text} !important; }}
        #global-container .global-card-1.global-gradient-{name} .global-text-muted {{ color: {on_muted} !important; }}
        #global-container .global-card-1.global-gradient-{name} .weather-icon {{ color: {on_icon} !important; }}
        """

    base_styles = f"""
        #global-container #global-weather-wrapper {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: {text_color} !important; margin: 20px auto; }}
        #global-container .global-card {{ border-radius: 24px; padding: 16px; }}
        #global-container .global-card-1 {{ background: {card_bg_1_solid} !important; }}
        #global-container .global-card-2 {{ background: {card_bg_2_solid} !important; }}
        #global-container .global-flex {{ display: flex; }} #global-container .global-grid {{ display: grid; }}
        #global-container .global-items-center {{ align-items: center; }} #global-container .global-justify-between {{ justify-content: space-between; }}
        #global-container .global-text-center {{ text-align: center; }} #global-container .global-text-right {{ text-align: right; }}
        #global-container .global-temp-large {{ font-size: 64px; line-height: 1; font-weight: 300; }}
        #global-container .global-text-muted {{ color: {text_muted} !important; font-size: 14px; }}
        #global-container .global-font-medium {{ font-weight: 500; }}
        #global-container .global-details-grid {{ grid-template-columns: 1fr auto; gap: 8px; font-size: 14px; align-items: center; }}
        #global-container .weather-icon {{ color: {icon_color}; }}
        #global-container .weather-icon svg {{ display: block; fill: currentColor; }}
        #global-container .aqi-icon {{ width: 14px; height: 14px; vertical-align: middle; margin-left: 4px; }}
        #global-container .humidity-icon {{ width: 14px; height: 14px; vertical-align: middle; margin-left: 4px; }}
        #global-container .global-icon-large .weather-icon, #global-container .global-icon-large .weather-icon svg {{ width: 64px; height: 64px; }}
    """
    
    view_mode = config.get("view_mode", "vertical")
    view_styles = ""
    if view_mode == "vertical":
        view_styles = """
            #global-container #global-weather-wrapper { display: grid; gap: 12px; max-width: 211px !important; }
            #global-container .vert-main-card-top { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px; }
            #global-container .vert-main-temp { font-size: 40px; line-height: 1; }
            #global-container .vert-feels-like { font-size: 13px; margin-top: 4px; }
            #global-container .vert-main-icon .weather-icon, #global-container .vert-main-icon .weather-icon svg { width: 48px; height: 48px; }
            #global-container .vert-hourly-forecast { display: grid; grid-template-columns: repeat(2, 1fr); margin-top: 1rem; gap: 1rem; text-align: center; }
            #global-container .vert-hourly-icon .weather-icon, #global-container .vert-hourly-icon .weather-icon svg { width: 22px; height: 22px; margin: 4px auto; }
            #global-container .vert-daily-forecast { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; text-align: center; }
            #global-container .vert-daily-item > div { margin-top: 4px; } #global-container .vert-daily-item .day { font-weight: 600; font-size: 13px; }
            #global-container .vert-daily-icon .weather-icon, #global-container .vert-daily-icon .weather-icon svg { width: 22px; height: 22px; margin: 0 auto; }
        """
    elif view_mode == "horizontal":
        view_styles = f"""
            #global-container #global-weather-wrapper {{ max-width: 600px; max-height: 200px !important; display: grid; grid-template-columns: 2fr 1.5fr; gap: 12px; }}
            #global-container .global-horizontal-right {{ display: grid; gap: 12px; }}
            #global-container .global-hourly-forecast {{ grid-template-columns: repeat(3, 1fr); margin-top: 1rem; }}
            #global-container .global-hourly-forecast .weather-icon, #global-container .global-hourly-forecast .weather-icon svg {{ width: 24px; height: 24px; margin: 4px auto; }}
            #global-container .global-daily-forecast {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-size: 12px; }}
            #global-container .global-daily-item .day {{ font-weight: 600; font-size: 12px; }}
            #global-container .global-daily-forecast .weather-icon, #global-container .global-daily-forecast .weather-icon svg {{ width: 22px; height: 22px; margin: 4px auto; }}
        """
    elif view_mode == "mini":
         view_styles = f"""
            #global-container #global-weather-wrapper {{ max-width: 200px !important; }}
            #global-container .global-mini-card {{ display: flex; flex-direction: column; height: 200px; box-sizing: border-box; }}
            #global-container .global-mini-main-content {{ flex-grow: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; }}
            #global-container .global-mini-temp {{ font-size: 44px; font-weight: 500; line-height: 1; }}
            #global-container .global-mini-hl {{ font-size: 14px; margin-top: 6px; }}
            #global-container .global-mini-info-bar {{ margin-top: auto; display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 12px; font-size: 14px; font-weight: 500; }}
            #global-container .global-mini-info-bar .weather-icon, #global-container .global-mini-info-bar .weather-icon svg {{ width: 24px; height: 24px; }}
            #global-container .global-mini-sunny {{ background-color: #FFFBEB !important; color: #725a03 !important;}}
            #global-container .global-mini-rainy {{ background-color: #E3F2FD !important; color: #0d47a1 !important;}}
            #global-container .global-mini-snowy {{ background-color: #E8F5E9 !important; color: #1b5e20 !important;}}
            #global-container .global-mini-stormy {{ background-color: #E8EAF6 !important; color: #1a237e !important;}}
            #global-container .global-mini-cloudy {{ background-color: #F5F5F5 !important; color: #212121 !important;}}
            #global-container.night_mode .global-mini-sunny {{ background-color: #4D411C !important; color: #FDE68A !important; }}
            #global-container.night_mode .global-mini-rainy {{ background-color: #1A344D !important; color: #90CAF9 !important; }}
            #global-container.night_mode .global-mini-snowy {{ background-color: #2F4220 !important; color: #C8E6C9 !important; }}
            #global-container.night_mode .global-mini-stormy {{ background-color: #282A4D !important; color: #C5CAE9 !important; }}
            #global-container.night_mode .global-mini-cloudy {{ background-color: #424242 !important; color: #E0E0E0 !important; }}
            /* The gradient-card rules above set a general on-gradient icon
               color with the same specificity as these pill-specific ones;
               since these come later in the generated CSS they'd win a tie
               anyway, but re-declaring the icon color explicitly here makes
               that not depend on source order. */
            #global-container .global-mini-info-bar.global-mini-sunny .weather-icon {{ color: #725a03 !important; }}
            #global-container .global-mini-info-bar.global-mini-rainy .weather-icon {{ color: #0d47a1 !important; }}
            #global-container .global-mini-info-bar.global-mini-snowy .weather-icon {{ color: #1b5e20 !important; }}
            #global-container .global-mini-info-bar.global-mini-stormy .weather-icon {{ color: #1a237e !important; }}
            #global-container .global-mini-info-bar.global-mini-cloudy .weather-icon {{ color: #212121 !important; }}
            #global-container.night_mode .global-mini-info-bar.global-mini-sunny .weather-icon {{ color: #FDE68A !important; }}
            #global-container.night_mode .global-mini-info-bar.global-mini-rainy .weather-icon {{ color: #90CAF9 !important; }}
            #global-container.night_mode .global-mini-info-bar.global-mini-snowy .weather-icon {{ color: #C8E6C9 !important; }}
            #global-container.night_mode .global-mini-info-bar.global-mini-stormy .weather-icon {{ color: #C5CAE9 !important; }}
            #global-container.night_mode .global-mini-info-bar.global-mini-cloudy .weather-icon {{ color: #E0E0E0 !important; }}
         """
    return base_styles + gradient_rules + view_styles

def generate_onigiri_fill_css():
    """Overrides compact weather layouts when Global is placed in Onigiri's grid."""
    radius = bento_integration.onigiri_widget_radius()
    radius_value = f"var(--onigiri-box-effect-radius, {radius}px)"
    return f"""
        .external-widget-container #global-container,
        .onigiri-external-overview-addon #global-container {{
            width: 100% !important;
            height: 100% !important;
            max-width: none !important;
            max-height: none !important;
            min-width: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            display: flex !important;
            box-sizing: border-box !important;
            border-radius: {radius_value} !important;
            overflow: hidden !important;
        }}
        .external-widget-container #global-container #global-weather-wrapper,
        .onigiri-external-overview-addon #global-container #global-weather-wrapper {{
            width: 100% !important;
            height: 100% !important;
            max-width: none !important;
            max-height: none !important;
            min-width: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            flex: 1 1 auto !important;
            box-sizing: border-box !important;
            align-items: stretch !important;
            border-radius: inherit !important;
        }}
        .external-widget-container #global-container .global-horizontal-left,
        .external-widget-container #global-container .global-horizontal-right,
        .external-widget-container #global-container .global-card,
        .onigiri-external-overview-addon #global-container .global-horizontal-left,
        .onigiri-external-overview-addon #global-container .global-horizontal-right,
        .onigiri-external-overview-addon #global-container .global-card {{
            min-width: 0 !important;
            min-height: 0 !important;
            box-sizing: border-box !important;
        }}
        .external-widget-container #global-container .global-card,
        .onigiri-external-overview-addon #global-container .global-card {{
            border-radius: {radius_value} !important;
        }}
        .external-widget-container #global-container #global-weather-wrapper > .global-card,
        .onigiri-external-overview-addon #global-container #global-weather-wrapper > .global-card {{
            width: 100% !important;
            justify-self: stretch !important;
            align-self: stretch !important;
        }}
        .external-widget-container #global-container .global-horizontal-left,
        .onigiri-external-overview-addon #global-container .global-horizontal-left {{
            display: flex !important;
            height: 100% !important;
        }}
        .external-widget-container #global-container .global-horizontal-left > .global-card,
        .onigiri-external-overview-addon #global-container .global-horizontal-left > .global-card {{
            width: 100% !important;
            height: 100% !important;
            flex: 1 1 auto !important;
        }}
        .external-widget-container #global-container .global-horizontal-right,
        .onigiri-external-overview-addon #global-container .global-horizontal-right {{
            height: 100% !important;
            align-content: stretch !important;
            grid-auto-rows: minmax(0, 1fr) !important;
        }}
        .external-widget-container #global-container .global-mini-card,
        .onigiri-external-overview-addon #global-container .global-mini-card {{
            width: 100% !important;
            height: 100% !important;
        }}
    """

def generate_html(weather_data, config=None, compact=False):
    """Generates the appropriate HTML block based on the selected view mode.

    `compact` trims the vertical layout's hourly forecast so it fits within
    Onigiri's fixed-height grid rows (a 4-row cell is too short for the full
    4-item forecast at the grid's default row height). It only affects the
    real widget render, not the settings-dialog preview, which always shows
    the full layout regardless of grid constraints.
    """
    if config is None:
        config = CONFIG
    view_mode = config.get("view_mode", "vertical")

    if not weather_data or "forecast" not in weather_data or "current" not in weather_data["forecast"]:
        return "<div class='global-text-center'>Could not parse weather data. If using a custom URL, ensure it includes 'current', 'hourly', and 'daily' parameters.</div>"

    # --- Data Extraction ---
    forecast = weather_data["forecast"]
    current = forecast["current"]; daily = forecast["daily"]; hourly = forecast["hourly"]

    # --- Dynamic Class Names ---
    gradient_class = get_gradient_class(current['weather_code'], current['is_day']) if config.get("enable_gradients", True) else ""
    
    # --- AQI and Humidity ---
    current_aqi = None
    if "aqi" in weather_data and weather_data["aqi"].get("hourly"):
        try:
            now_unix = int(time.time())
            aqi_hourly_times_str = weather_data["aqi"]["hourly"]["time"]
            closest_time_str = min(aqi_hourly_times_str, key=lambda t: abs(datetime.fromisoformat(t).timestamp() - now_unix))
            idx = aqi_hourly_times_str.index(closest_time_str)
            current_aqi = weather_data["aqi"]["hourly"]["us_aqi"][idx]
        except (ValueError, IndexError): pass
    
    humidity_icon_html = f'<img src="{load_image_as_base64("humidity.png")}" class="humidity-icon">'
    
    # --- HTML Generation for Views ---
    if view_mode == "vertical":
        hourly_html = ""
        now_dt = datetime.now()
        start_idx = next((i for i, t in enumerate(hourly['time']) if datetime.fromisoformat(t) > now_dt), 0)
        hourly_count = 2 if compact else 4
        for i in range(start_idx, min(start_idx + hourly_count, len(hourly['time']))):
            hour_dt = datetime.fromisoformat(hourly['time'][i])
            hourly_html += f"""<div>
                <div class="vert-hourly-icon">{get_icon(hourly['weather_code'][i], 7 <= hour_dt.hour < 19)}</div>
                <div class="global-text-muted">{hour_dt.strftime('%H:00')}</div>
                <div class="global-font-medium">{hourly['temperature_2m'][i]:+.0f}°</div>
            </div>"""

        daily_html = ""
        for i in range(4):
            day_label = "Today" if i == 0 else datetime.fromisoformat(daily['time'][i]).strftime('%a')
            daily_html += f"""<div class='vert-daily-item'>
                <div class="day">{day_label}</div>
                <div class="vert-daily-icon">{get_icon(daily['weather_code'][i], True)}</div>
                <div class="global-font-medium">{daily['temperature_2m_max'][i]:+.0f}°</div>
                <div class="global-text-muted">{daily['temperature_2m_min'][i]:+.0f}°</div>
            </div>"""
        feels_like_temp = current.get('apparent_temperature', current['temperature_2m'])
        
        return f"""
            <div class="global-card global-card-1 {gradient_class}">
                <div class="vert-main-card-top">
                    <div>
                        <div class="vert-main-temp">{current['temperature_2m']:+.0f}°</div>
                        <div class="vert-feels-like global-text-muted">Feels like: {feels_like_temp:.0f}°</div>
                    </div>
                    <div class="vert-main-icon">{get_icon(current['weather_code'], current['is_day'])}</div>
                </div> <div class="vert-hourly-forecast">{hourly_html}</div>
            </div>
            <div class="global-card global-card-2">
                <div class="global-grid global-details-grid">
                    <span>Air Quality Index:</span><span class="global-text-right global-font-medium">{get_aqi_text(current_aqi)}</span>
                    <span>Humidity:</span><span class="global-text-right global-font-medium">{current['relative_humidity_2m']}% {humidity_icon_html}</span>
                </div>
            </div>
            <div class="global-card global-card-2"><div class="vert-daily-forecast">{daily_html}</div></div>"""

    if view_mode == "horizontal":
        hourly_html = ""
        now_dt = datetime.now()
        start_idx = next((i for i, t in enumerate(hourly['time']) if datetime.fromisoformat(t) > now_dt), 0)
        for i in range(start_idx, min(start_idx + 3, len(hourly['time']))):
            hour_dt = datetime.fromisoformat(hourly['time'][i])
            hourly_html += f"""<div class='global-text-center'>
                <div class="global-text-muted">{hour_dt.strftime('%H:00')}</div>
                {get_icon(hourly['weather_code'][i], 7 <= hour_dt.hour < 19)}
                <div class="global-font-medium">{hourly['temperature_2m'][i]:+.0f}°</div>
            </div>"""
        daily_html = ""
        for i in range(4):
            day_label = "Today" if i == 0 else datetime.fromisoformat(daily['time'][i]).strftime('%a')
            daily_html += f"""<div class='global-text-center global-daily-item'>
                <div class="day">{day_label}</div>{get_icon(daily['weather_code'][i], True)}
                <div class="global-font-medium">{daily['temperature_2m_max'][i]:+.0f}°</div>
                <div class="global-text-muted">{daily['temperature_2m_min'][i]:+.0f}°</div>
            </div>"""
        
        return f"""
            <div class="global-horizontal-left">
                 <div class="global-card global-card-1 {gradient_class}" style="height: 180px;">
                    <div class="global-flex global-justify-between global-items-center">
                        <div class="global-temp-large">{current['temperature_2m']:.0f}°</div>
                        <div class="global-icon-large">{get_icon(current['weather_code'], current['is_day'])}</div>
                    </div>
                    <div class="global-text-muted">H: {daily['temperature_2m_max'][0]:+.0f}° L: {daily['temperature_2m_min'][0]:+.0f}°</div>
                    <div class="global-grid global-hourly-forecast">{hourly_html}</div>
                </div>
            </div>
            <div class="global-horizontal-right">
                <div class="global-card global-card-2">
                    <div class="global-grid global-details-grid">
                        <span>Air Quality:</span><span class="global-text-right global-font-medium">{get_aqi_text(current_aqi)}</span>
                        <span>Humidity:</span><span class="global-text-right global-font-medium">{current['relative_humidity_2m']}% {humidity_icon_html}</span>
                    </div>
                </div><div class="global-card global-card-2"><div class="global-daily-forecast">{daily_html}</div></div>
            </div>"""

    if view_mode == "mini":
        weather_class_map = {
            0: "sunny", 1: "sunny",
            51: "rainy", 53: "rainy", 55: "rainy", 61: "rainy", 63: "rainy", 65: "rainy", 80: "rainy", 81: "rainy", 82: "rainy",
            56: "snowy", 57: "snowy", 66: "snowy", 67: "snowy", 71: "snowy", 73: "snowy", 75: "snowy", 77: "snowy", 85: "snowy", 86: "snowy",
            95: "stormy", 96: "stormy", 99: "stormy",
        }
        weather_class = "global-mini-" + weather_class_map.get(current['weather_code'], "cloudy")
        weather_description = WMO_MAP.get(current['weather_code'], ("Unknown",))[0]

        return f"""
             <div class="global-card global-card-1 global-mini-card {gradient_class}">
                <div class="global-mini-main-content">
                    <div class="global-mini-temp">{current['temperature_2m']:.0f}°</div>
                    <div class="global-mini-hl global-text-muted">H: {daily['temperature_2m_max'][0]:+.0f}° L: {daily['temperature_2m_min'][0]:+.0f}°</div>
                </div>
                <div class="global-mini-info-bar {weather_class}">
                    <span class="icon">{get_icon(current['weather_code'], current['is_day'])}</span>
                    <span>{weather_description}</span>
                </div>
            </div>"""
    return ""

# --- Anki Integration ---
cached_weather_html = None

def add_weather_to_deck_browser(deck_browser: aqt.deckbrowser.DeckBrowser, content: aqt.deckbrowser.DeckBrowserContent):
    """Appends the weather widget to the deck browser's stats area."""
    global cached_weather_html
    
    if cached_weather_html is None:
        weather_data = get_weather_data()
        html_content = generate_html(weather_data, compact=bento_integration.is_onigiri_detected())
        css = generate_css(mw.pm.night_mode())
        wrapper_class = "night_mode" if mw.pm.night_mode() else ""
        sizing_css = bento_integration.sizing_css(
            "#global-container",
            "#global-container #global-weather-wrapper",
            CONFIG,
            default_width=211,
            default_height=300,
        )
        onigiri_css = generate_onigiri_fill_css()
        cached_weather_html = f"<div id='global-container' class='{wrapper_class}'><style>{css}{sizing_css}{onigiri_css}</style><div id='global-weather-wrapper'>{html_content}</div></div>"

    content.stats += cached_weather_html

def reset_weather_cache(*args, **kwargs):
    """Clears the cached HTML, forcing a refresh."""
    global cached_weather_html
    cached_weather_html = None

def on_theme_change():
    """Reset cache and refresh deck browser when theme changes."""
    reset_weather_cache()
    if mw.state == "deckBrowser":
        mw.deckBrowser.refresh()



_is_settings_open = False
def debounce_settings(func):
    def wrapper(*args, **kwargs):
        global _is_settings_open
        if _is_settings_open:
            return
        _is_settings_open = True
        try:
            return func()
        finally:
            _is_settings_open = False
    return wrapper

@debounce_settings
def show_settings():
    dialog = SettingsDialog(mw, config=CONFIG, addon_name=__name__)
    dialog.exec()
    # After the dialog is closed, reset the cache so style changes are reflected.
    reset_weather_cache()

gui_hooks.deck_browser_will_render_content.append(add_weather_to_deck_browser)
gui_hooks.reviewer_will_end.append(reset_weather_cache)
gui_hooks.sync_did_finish.append(reset_weather_cache)
gui_hooks.theme_did_change.append(on_theme_change)

bento_integration.register_widget("Global", settings_callback=show_settings)
bento_integration.add_menu_action("Global Settings", show_settings)
