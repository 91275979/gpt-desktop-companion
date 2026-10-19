"""从本机网络请求的公网出口定位；不读取 Windows Widget，不保存 IP。"""
from dataclasses import dataclass
from http_client import number

IP_LOCATION_URL = ('https://ipwho.is/?fields=success,message,city,region,country,'
                   'country_code,latitude,longitude,timezone.id')


@dataclass(frozen=True)
class IPLocation:
    city: str
    country: str
    region: str
    latitude: float
    longitude: float
    timezone: str


def parse_ip_location(data):
    if not isinstance(data, dict) or data.get('success') is not True:
        raise ValueError('公网 IP 定位失败')
    latitude, longitude = number(data['latitude']), number(data['longitude'])
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('IP 定位经纬度无效')
    city, country = data.get('city'), data.get('country')
    if not isinstance(city, str) or not city.strip() or not isinstance(country, str) or not country.strip():
        raise ValueError('IP 定位缺少城市或国家')
    timezone = data.get('timezone', {}).get('id') or 'auto'
    if not isinstance(timezone, str):
        raise ValueError('IP 定位时区无效')
    return IPLocation(city.strip(), country.strip(), str(data.get('region', '')),
                      latitude, longitude, timezone)
