#!/usr/bin/env python3
"""
每日自動抓取台灣農業部農糧署、漁業署行情資料
輸出至 docs/prices.json，供 GitHub Pages 靜態托管
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# ── 品名分類白名單（對應 MarketPriceService.swift 邏輯）──────────────────────
VEGETABLE_KW = [
    "高麗菜","甘藍","包心菜","白菜","小白菜","大白菜","菠菜","空心菜","蕹菜","莧菜","茼蒿",
    "韭菜","蒜苗","蔥","洋蔥","芹菜","青椒","甜椒","彩椒","番茄","小番茄","聖女番茄",
    "茄子","苦瓜","冬瓜","南瓜","絲瓜","菜瓜","胡瓜","小黃瓜","蘿蔔","白蘿蔔","青花菜",
    "花椰菜","花菜","玉米","甜玉米","糯玉米","秋葵","豌豆","毛豆","豇豆","四季豆","菜豆",
    "長豇豆","敏豆","蘆筍","石刁柏","竹筍","綠竹筍","麻竹筍","桂竹筍","芋頭","山藥","淮山",
    "地瓜","甘藷","番薯","馬鈴薯","洋芋","蓮藕","牛蒡","薑","辣椒","地瓜葉","甘藷葉","龍鬚菜",
    "菜心","芥藍","格藍菜","萵苣","A菜","福山萵苣","茭白筍","筊白筍","菱角","蓮霧",
    "刺莧","野莧","打某菜","長茄","矮性茄","金瓜","土豆",
]
FRUIT_KW = [
    "香蕉","芒果","鳳梨","西瓜","哈密瓜","木瓜","芭樂","番石榴","蓮霧","楊桃","釋迦",
    "番荔枝","百香果","西番蓮","火龍果","荔枝","龍眼","柑橘","柳橙","橘子","檸檬","葡萄柚",
    "葡萄","草莓","奇異果","蘋果","梨","水梨","枇杷","李子","梅","桃","杏","柿子","棗",
    "榴槤","山竹","紅毛丹","芭蕉","鳳梨釋迦","玫瑰桃","夏雪梨","福壽梨",
]
FLOWER_KW = ["玫瑰","菊花","百合","唐菖蒲","非洲菊","文心蘭","石斛蘭","蝴蝶蘭","鬱金香","桔梗"]
SEAFOOD_KW = ["魚","蝦","蟹","蟳","蚵","牡蠣","蛤","鱸","虱目","吳郭","鮪","烏魚","帶魚",
              "鯖","鯧","鱲","魽","鰱","透抽","花枝","龍蝦","小卷","萬引"]

# ── API 品名 → 顯示關鍵字 反向對照表（對應 MarketPriceService.apiNameAliases）──
# 農業部 API 品名（如「葉用甘藷」）→ App 顯示名稱（如「地瓜葉」）
API_ALIAS: dict[str, list[str]] = {
    "地瓜葉": ["葉用甘藷", "甘藷葉", "地瓜葉", "番薯葉"],
    "小黃瓜": ["小黃瓜", "胡瓜"],
    "空心菜": ["空心菜", "蕹菜"],
    "蕹菜":   ["蕹菜", "空心菜"],
    "莧菜":   ["莧菜", "刺莧", "野莧"],
    "龍鬚菜": ["龍鬚菜", "龍鬚", "佛手瓜嫩莖"],
    "茼蒿":   ["茼蒿", "打某菜"],
    "芥藍":   ["芥藍", "格藍菜"],
    "白蘿蔔": ["白蘿蔔", "蘿蔔"],
    "高麗菜": ["高麗菜", "甘藍", "包心菜"],
    "甘藍":   ["甘藍", "高麗菜", "包心菜"],
    "菜豆":   ["菜豆", "長豇豆", "豇豆", "四季豆", "敏豆"],
    "四季豆": ["四季豆", "菜豆", "敏豆", "長豇豆"],
    "絲瓜":   ["絲瓜", "菜瓜"],
    "苦瓜":   ["苦瓜", "涼瓜"],
    "南瓜":   ["南瓜", "金瓜"],
    "茄子":   ["茄子", "矮性茄", "長茄"],
    "甜椒":   ["甜椒", "彩椒", "青椒"],
    "玉米":   ["玉米", "甜玉米", "糯玉米"],
    "竹筍":   ["竹筍", "綠竹筍", "麻竹筍", "桂竹筍", "烏殼綠竹"],
    "茭白筍": ["茭白筍", "筊白筍", "茭白"],
    "芋頭":   ["芋頭", "芋", "白芋"],
    "山藥":   ["山藥", "淮山", "長山藥", "日本山藥"],
    "蓮藕":   ["蓮藕", "藕"],
    "蘆筍":   ["蘆筍", "石刁柏"],
    "菱角":   ["菱角", "菱"],
    "馬鈴薯": ["馬鈴薯", "洋芋", "土豆"],
    "地瓜":   ["甘藷", "地瓜", "番薯"],
    "芭樂":   ["芭樂", "番石榴"],
    "百香果": ["百香果", "西番蓮"],
    "釋迦":   ["釋迦", "番荔枝"],
}
# 建立反向查表：API品名片段 → 顯示關鍵字
_REVERSE_ALIAS: dict[str, str] = {}
for display, api_names in API_ALIAS.items():
    for api_name in api_names:
        _REVERSE_ALIAS[api_name] = display

def normalize_name(crop_name: str) -> str:
    """將 API 回傳品名正規化為 App 顯示關鍵字，找不到則原樣回傳"""
    for api_name, display in _REVERSE_ALIAS.items():
        if api_name in crop_name:
            return display
    return crop_name

def classify(name: str) -> str | None:
    base = name.split("-")[0].split("－")[0].strip()
    if any(kw in base for kw in FLOWER_KW):
        return None
    if any(kw in base for kw in VEGETABLE_KW):
        return "蔬菜"
    if any(kw in base for kw in FRUIT_KW):
        return "水果"
    if any(kw in base for kw in SEAFOOD_KW):
        return "漁貨"
    return None

# ── 日期工具（民國年格式）─────────────────────────────────────────────────────
def roc_date(offset_days: int = 0) -> str:
    d = datetime.now() - timedelta(days=offset_days)
    roc_year = d.year - 1911
    return f"{roc_year}.{d.month:02d}.{d.day:02d}"

def roc_date_no_dots(offset_days: int = 0) -> str:
    d = datetime.now() - timedelta(days=offset_days)
    roc_year = d.year - 1911
    return f"{roc_year}{d.month:02d}{d.day:02d}"

def fetch_json(url: str) -> list | dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SolarTermApp/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        print(f"  ⚠ fetch failed: {url[:80]} — {e}")
        return None

# ── 農業部農糧署行情 ──────────────────────────────────────────────────────────
AGRI_BASE = "https://data.moa.gov.tw/api/v1/AgriProductsTransType/"

def fetch_agri_page(start_date: str, end_date: str, page: int = 1) -> tuple[list, bool]:
    params = urllib.parse.urlencode({
        "Start_time": start_date,
        "End_time":   end_date,
        "Page":       page,
    })
    data = fetch_json(f"{AGRI_BASE}?{params}")
    if not data:
        return [], False
    records = data.get("Data") or []
    # 彈性解析 Next：可能是 bool 或字串
    raw_next = data.get("Next", False)
    has_next = (raw_next is True) or (str(raw_next).lower() == "true")
    return records, has_next

def fetch_all_agri(lookback: int = 3) -> list[dict]:
    for offset in range(lookback):
        date_str = roc_date(offset)
        print(f"  農業部 {date_str}…", end=" ")
        records, has_next = fetch_agri_page(date_str, date_str)
        page = 2
        while has_next and page <= 10:
            more, has_next = fetch_agri_page(date_str, date_str, page)
            records.extend(more)
            page += 1
        print(f"{len(records)} 筆")
        if records:
            return records
    return []

# 全量抓取不穩定的品名，需指定 CropName 補查
# 對應 Swift 的 forceSupplementAgriKeywords
SUPPLEMENT_QUERIES: list[tuple[str, str]] = [
    # (顯示名稱, API查詢品名)
    ("地瓜葉", "葉用甘藷"),
    ("地瓜葉", "甘藷葉"),
    ("莧菜",   "莧菜"),
    ("龍鬚菜", "龍鬚菜"),
    ("地瓜",   "甘藷"),
    ("蘆筍",   "石刁柏"),
    ("山藥",   "淮山"),
]

def fetch_agri_by_name(crop_name: str, display_name: str, lookback: int = 3) -> list[dict]:
    """以指定 CropName 查詢，結果的 CropName 強制設為 display_name"""
    params_base = {"End_time": "", "Start_time": "", "CropName": crop_name}
    for offset in range(lookback):
        date_str = roc_date(offset)
        params = urllib.parse.urlencode({
            "Start_time": date_str,
            "End_time":   date_str,
            "CropName":   crop_name,
        })
        data = fetch_json(f"{AGRI_BASE}?{params}")
        if not data:
            continue
        records = data.get("Data") or []
        if records:
            # 強制設定 CropName 為 display_name，讓後續 normalize_name 能對到
            for r in records:
                r["CropName"] = display_name
            return records
    return []

def parse_float(val) -> float:
    try:
        if isinstance(val, (int, float)):
            return float(val)
        return float(str(val).strip()) if val else 0.0
    except:
        return 0.0

def agri_to_price(r: dict) -> dict | None:
    crop = r.get("CropName", "")
    cat  = classify(crop)
    if cat is None:
        return None
    date         = r.get("TransDate", "")
    market       = r.get("MarketName", "")
    high         = parse_float(r.get("Upper_Price", 0))
    mid          = parse_float(r.get("Middle_Price", 0))
    low          = parse_float(r.get("Lower_Price", 0))
    if mid <= 0:
        return None
    display_name = normalize_name(crop)  # 「葉用甘藷」→「地瓜葉」等
    return {
        "id":          f"{date}-{display_name}-{market}",
        "date":        date,
        "productName": display_name,
        "market":      market,
        "highPrice":   round(high, 1),
        "midPrice":    round(mid, 1),
        "lowPrice":    round(low, 1),
        "category":    cat,
    }

# ── 農業部漁業署行情 ──────────────────────────────────────────────────────────
AQUATIC_BASE = "https://data.moa.gov.tw/Service/OpenData/FromM/AquaticTransData.aspx"

def fetch_all_aquatic(lookback: int = 3) -> list[dict]:
    for offset in range(lookback):
        date_str = roc_date_no_dots(offset)
        params = urllib.parse.urlencode({
            "IsTransData": 1,
            "UnitId":      "039",
            "StartDate":   date_str,
            "EndDate":     date_str,
            "Num":         1000,
        })
        print(f"  漁業署 {date_str}…", end=" ")
        records = fetch_json(f"{AQUATIC_BASE}?{params}")
        if records is None:
            records = []
        # API 有時直接回傳陣列，有時包在物件內
        if isinstance(records, dict):
            records = records.get("Data") or records.get("data") or []
        print(f"{len(records)} 筆")
        if records:
            return records
    return []

def aquatic_to_price(r: dict) -> dict | None:
    fish_name = r.get("魚貨名稱", "")
    if not fish_name or fish_name in ("休市", "-", ""):
        return None
    raw_date = r.get("交易日期", "")
    if len(raw_date) == 7:
        dot_date = f"{raw_date[:3]}.{raw_date[3:5]}.{raw_date[5:]}"
    else:
        dot_date = raw_date
    market = r.get("市場名稱", "")
    mid    = parse_float(r.get("中價", 0))
    if mid <= 0:
        return None
    return {
        "id":          f"{raw_date}-{fish_name}-{market}",
        "date":        dot_date,
        "productName": fish_name,
        "market":      market,
        "highPrice":   round(parse_float(r.get("上價", mid)), 1),
        "midPrice":    round(mid, 1),
        "lowPrice":    round(parse_float(r.get("下價", mid)), 1),
        "category":    "漁貨",
    }

# ── 去重 ──────────────────────────────────────────────────────────────────────
def deduplicate(prices: list[dict]) -> list[dict]:
    seen = set()
    out  = []
    for p in prices:
        if p["id"] not in seen:
            seen.add(p["id"])
            out.append(p)
    return out

# ── 主程式 ────────────────────────────────────────────────────────────────────
def main():
    print("=== 農業部農糧署行情 ===")
    agri_raw = fetch_all_agri()

    # 補查全量抓取不穩定的品名（地瓜葉、莧菜等）
    print("  補查特定品名…")
    seen_display = set(r.get("CropName","") for r in agri_raw)
    for display_name, api_name in SUPPLEMENT_QUERIES:
        if display_name not in seen_display:
            extra = fetch_agri_by_name(api_name, display_name)
            if extra:
                print(f"    {display_name}（{api_name}）→ {len(extra)} 筆")
                agri_raw.extend(extra)
                seen_display.add(display_name)

    agri_prices = [p for r in agri_raw for p in [agri_to_price(r)] if p]

    print("\n=== 農業部漁業署行情 ===")
    aqua_raw    = fetch_all_aquatic()
    aqua_prices = [p for r in aqua_raw for p in [aquatic_to_price(r)] if p]

    all_prices = deduplicate(agri_prices + aqua_prices)

    # 統計
    cats = {}
    for p in all_prices:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    print(f"\n✅ 合計 {len(all_prices)} 筆有效行情")
    for cat, count in sorted(cats.items()):
        print(f"   {cat}: {count} 筆")

    # 寫出 JSON
    import os
    os.makedirs("docs", exist_ok=True)
    meta = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count":     len(all_prices),
        "prices":    all_prices,
    }
    out_path = "docs/prices.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n💾 已寫入 {out_path}")

if __name__ == "__main__":
    main()
