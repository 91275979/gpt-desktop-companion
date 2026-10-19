"""本地偏好：严格校验，损坏配置回退，原子保存。"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
SIZES = (150, 180, 220)


def load_settings(path):
    result = dict(character_size=180, always_on_top=True, panel_visible=False, position=None,
                  dashboard_page='usage', weather_location='', market_refresh_minutes=2,
                  weather_refresh_minutes=20, watchlist=[], market_color_scheme='cn',
                  weather_location_mode='ip')
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return result
    if not isinstance(data, dict):
        return result
    if data.get('dashboard_page') in ('usage', 'weather', 'markets'):
        result['dashboard_page'] = data['dashboard_page']
    if data.get('market_color_scheme') in ('cn', 'global'):
        result['market_color_scheme'] = data['market_color_scheme']
    if data.get('weather_location_mode') in ('ip', 'manual'):
        result['weather_location_mode'] = data['weather_location_mode']
    if isinstance(data.get('weather_location'), str):
        result['weather_location'] = data['weather_location'].strip()[:200]
    for key, low, high in (('market_refresh_minutes', 1, 5), ('weather_refresh_minutes', 15, 30)):
        if type(data.get(key)) is int:
            result[key] = max(low, min(high, data[key]))
    if isinstance(data.get('watchlist'), list):
        result['watchlist'] = [s for s in data['watchlist'] if isinstance(s, str)][:100]
    if type(data.get("character_size")) is int and data["character_size"] in SIZES:
        result["character_size"] = data["character_size"]
    for key in ("always_on_top", "panel_visible"):
        if type(data.get(key)) is bool:
            result[key] = data[key]
    pos = data.get("position")
    if isinstance(pos, dict) and all(type(pos.get(k)) is int and abs(pos[k]) < 1000000 for k in ("x", "y")):
        result["position"] = pos
    return result


def save_settings(path, data):
    path = Path(path)
    temp = path.with_suffix(".json.tmp")
    try:
        try:
            existing = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            existing = {}
        data = {**(existing if isinstance(existing, dict) else {}), **data}
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return True
    except OSError:
        return False
