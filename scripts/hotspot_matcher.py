"""eBird 热点匹配 + 高德地理编码兜底"""

import re
import math
from difflib import SequenceMatcher
from functools import lru_cache

import requests

# ---- 省份 → eBird ISO 3166-2 代码 ----
PROVINCE_TO_ISO = {
    '北京市': 'CN-11',
    '上海市': 'CN-31',
    '天津市': 'CN-12',
    '重庆市': 'CN-50',
    '河北省': 'CN-13',
    '山西省': 'CN-14',
    '内蒙古自治区': 'CN-15',
    '辽宁省': 'CN-21',
    '吉林省': 'CN-22',
    '黑龙江省': 'CN-23',
    '江苏省': 'CN-32',
    '浙江省': 'CN-33',
    '安徽省': 'CN-34',
    '福建省': 'CN-35',
    '江西省': 'CN-36',
    '山东省': 'CN-37',
    '河南省': 'CN-41',
    '湖北省': 'CN-42',
    '湖南省': 'CN-43',
    '广东省': 'CN-44',
    '广西壮族自治区': 'CN-45',
    '海南省': 'CN-46',
    '四川省': 'CN-51',
    '贵州省': 'CN-52',
    '云南省': 'CN-53',
    '西藏自治区': 'CN-54',
    '陕西省': 'CN-61',
    '甘肃省': 'CN-62',
    '青海省': 'CN-63',
    '宁夏回族自治区': 'CN-64',
    '新疆维吾尔自治区': 'CN-65',
    # 兼容记录中心可能出现的变体
    '新疆维吾尔族自治区': 'CN-65',
    '台湾省': 'CN-71',
    '香港特别行政区': 'CN-91',
    '澳门特别行政区': 'CN-92',
}


def fetch_hotspots(province_name: str, ebird_key: str) -> list[dict]:
    """从 eBird API 拉取指定省份的全部热点。

    返回列表，每项含 locId / locName / lat / lng 等字段。
    注意：Streamlit 环境使用 `@st.cache_data` 替代此函数做缓存。
    """
    iso_code = PROVINCE_TO_ISO.get(str(province_name).strip())
    if not iso_code:
        return []

    url = f"https://api.ebird.org/v2/ref/hotspot/{iso_code}"
    params = {"fmt": "json"}
    headers = {"X-eBirdApiToken": ebird_key}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def _extract_cn(name: str) -> str:
    """从 eBird 热点名中提取中文部分。

    '天坛公园 (Temple of Heaven)' → '天坛公园'
    """
    m = re.match(r'^(.+?)\s*(?:\(.+)?$', name)
    return m.group(1).strip() if m else name.strip()


def _jaccard(a: str, b: str) -> float:
    """两字符串的 Jaccard 字符集相似度。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0
    return len(sa & sb) / len(sa | sb)


def match_location(location_name: str, hotspots: list[dict]) -> dict | None:
    """将观鸟地点名匹配到 eBird 热点。

    四级策略：
        1. 精确匹配（中文名 == 热点中文名）
        2. 子串匹配（地点名是热点名子串，选最短的）
        3. 反向子串（热点名是地点名子串）
        4. 字符相似度（SequenceMatcher ≥ 0.6 或 Jaccard ≥ 0.5）

    返回：匹配到的热点 dict，或 None
    """
    name = str(location_name).strip()
    if not name or not hotspots:
        return None

    # Level 1 — 精确
    for h in hotspots:
        if h.get('locName', '') == name or _extract_cn(h.get('locName', '')) == name:
            return h

    # Level 2 — 子串（地点名 ⊂ 热点名）
    candidates = []
    for h in hotspots:
        cn = _extract_cn(h.get('locName', ''))
        if name in cn:
            candidates.append((h, len(cn) - len(name)))
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    # Level 3 — 反向子串（热点名 ⊂ 地点名）
    for h in hotspots:
        cn = _extract_cn(h.get('locName', ''))
        if cn and cn in name:
            return h

    # Level 4 — 相似度
    best_via_ratio = (None, 0)
    best_via_jac = (None, 0)
    for h in hotspots:
        cn = _extract_cn(h.get('locName', ''))
        if not cn:
            continue
        r = SequenceMatcher(None, name, cn).ratio()
        if r > best_via_ratio[1]:
            best_via_ratio = (h, r)
        j = _jaccard(name, cn)
        if j > best_via_jac[1]:
            best_via_jac = (h, j)
    if best_via_ratio[1] >= 0.6:
        return best_via_ratio[0]
    if best_via_jac[1] >= 0.5:
        return best_via_jac[0]

    return None


def find_nearest_hotspot(lat: float, lng: float, ebird_key: str, dist: int = 5) -> dict | None:
    """按 GPS 坐标搜索最近 eBird 热点。

    Args:
        lat, lng: 坐标（WGS-84 最佳，GCJ-02 也可用）
        ebird_key: eBird API Key
        dist: 搜索半径（km），默认 5

    Returns:
        最近的热点 dict（含 locId/locName/lat/lng），或 None
    """
    url = "https://api.ebird.org/v2/ref/hotspot/geo"
    params = {"lat": lat, "lng": lng, "dist": dist, "fmt": "json"}
    headers = {"X-eBirdApiToken": ebird_key}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            hotspots = resp.json()
            if hotspots:
                return hotspots[0]  # API 按距离排序，第一即最近
    except Exception:
        pass
    return None


def geocode_amap(address: str, province: str, amap_key: str) -> tuple[float | None, float | None]:
    """高德地图地理编码：地名 → GPS。

    返回值：(latitude, longitude)，均为 float。失败返回 (None, None)。
    """
    url = "https://restapi.amap.com/v3/geocode/geo"
    # 加省份前缀提高准确率
    query = f"{province}{address}" if province else address
    params = {"key": amap_key, "address": query}
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if data.get("status") == "1" and data.get("count") != "0":
            lng_lat = data["geocodes"][0]["location"]  # "116.410829,39.881913"
            lng_str, lat_str = lng_lat.split(",")
            return float(lat_str), float(lng_str)
    except Exception:
        pass
    return None, None


def reverse_geocode_amap(lat: float, lng: float, amap_key: str) -> str | None:
    """高德逆地理编码：GPS → 附近 POI 名称。

    返回最近的 POI 名称，无 POI 则返回结构化地址片段。失败返回 None。
    """
    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "key": amap_key,
        "location": f"{lng},{lat}",
        "extensions": "all",
        "poitype": "",  # 不限 POI 类型
        "radius": 1000,  # 1km 内
        "roadlevel": 0,
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if data.get("status") == "1":
            regeo = data.get("regeocode", {})
            # 优先取最近 POI
            pois = regeo.get("pois", [])
            if pois:
                return pois[0].get("name")
            # 无 POI，取地址字段
            addr = regeo.get("addressComponent", {})
            parts = [
                addr.get(k, "")
                for k in ("township", "streetNumber", "neighborhood")
            ]
            name = "".join(p for p in parts if p)
            if name:
                return name
    except Exception:
        pass
    return None


# ---- 本地距离计算（避免逐个调 API） ----

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine 公式计算两点间球面距离（公里）。"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_hotspot_local(lat: float, lng: float,
                               hotspots: list[dict],
                               max_dist_km: float = 5.0) -> dict | None:
    """在本地热点列表中按 Haversine 距离找最近的（≤ max_dist_km）。

    相比逐坐标调 eBird /geo API，一次性拉全省热点再本地匹配快 10~50 倍。
    """
    best, best_dist = None, float('inf')
    for h in hotspots:
        hlat = h.get('lat')
        hlng = h.get('lng')
        if hlat is None or hlng is None:
            continue
        d = _haversine_km(lat, lng, float(hlat), float(hlng))
        if d < best_dist and d <= max_dist_km:
            best_dist = d
            best = h
    return best
