#!/usr/bin/env python3
"""
每日自動抓取台灣農業部農糧署、漁業署行情資料
輸出至 docs/prices.json，供 GitHub Pages 靜態托管
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
import os

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
    date     = r.get("TransDate", "")
    market   = r.get("MarketName", "")
    high     = parse_float(r.get("Upper_Price", 0))
    mid      = parse_float(r.get("Middle_Price", 0))
    low      = parse_float(r.get("Lower_Price", 0))
    if mid <= 0:
        return None
    return {
        "id":          f"{date}-{crop}-{market}",
        "date":        date,
        "productName": crop,
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
    agri_raw    = fetch_all_agri()
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
