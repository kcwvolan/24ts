#!/usr/bin/env python3
"""
每日自動抓取台灣農業部農糧署、漁業署行情資料
輸出至 docs/prices.json，供 GitHub Pages 靜態托管
"""
from __future__ import annotations
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# Mac Python 常見問題：未安裝系統根憑證，略過 SSL 驗證（僅限政府開放資料 API）
_SSL_CTX = ssl._create_unverified_context()

# ── 品名分類白名單（對應 MarketPriceService.swift 邏輯）──────────────────────
VEGETABLE_KW = [
    "高麗菜","甘藍","包心菜","白菜","小白菜","大白菜","菠菜","空心菜","蕹菜","莧菜","茼蒿",
    "韭菜","蒜苗","蔥","洋蔥","芹菜","青椒","甜椒","彩椒","番茄","小番茄","聖女番茄",
    "茄子","苦瓜","冬瓜","南瓜","絲瓜","菜瓜","胡瓜","小黃瓜","蘿蔔","白蘿蔔","青花菜",
    "花椰菜","花菜","玉米","甜玉米","糯玉米","秋葵","豌豆","毛豆","豇豆","四季豆","菜豆",
    "長豇豆","敏豆","蘆筍","石刁柏","竹筍","綠竹筍","麻竹筍","桂竹筍","芋頭","山藥","淮山",
    "地瓜","甘藷","甘薯","番薯","馬鈴薯","洋芋","蓮藕","牛蒡","薑","辣椒",
    "地瓜葉","甘藷葉","甘薯葉","龍鬚菜","薯蕷",
    "菜心","芥藍","格藍菜","萵苣","A菜","福山萵苣","茭白筍","筊白筍","菱角",
    "刺莧","野莧","打某菜","長茄","矮性茄","金瓜","土豆",
    # 菇類（需優先列於 VEGETABLE_KW，避免「杏」字被 FRUIT_KW 的「杏」誤判為水果）
    "杏鮑菇","香菇","金針菇","秀珍菇","美白菇","鴻喜菇","舞茸","木耳","洋菇",
    # 其他蔬菜補充（大暑/立秋節氣食材）
    "金針","金針花",  # 黃花菜（食用花蕾）；「金針菇」已在前，此只補「金針」本身避免漏分類
    "櫻桃蘿蔔",      # 小眾蔬菜，「蘿蔔」子字串已可由 VEGETABLE_KW 命中，此行為文件保留
]
FRUIT_KW = [
    "香蕉","芒果","鳳梨","旺來","西瓜","哈密瓜","木瓜","芭樂","番石榴","蓮霧","楊桃","釋迦",
    "番荔枝","百香果","西番蓮","火龍果","荔枝","龍眼","柑橘","柳橙","橘子","檸檬","葡萄柚",
    "葡萄","草莓","奇異果","蘋果","梨","水梨","枇杷","李子","梅","桃","杏","柿子","棗",
    "榴槤","山竹","紅毛丹","芭蕉","鳳梨釋迦","玫瑰桃","夏雪梨","福壽梨",
]
FLOWER_KW = [
    # 常見花市切花（需在 SEAFOOD_KW 比對前排除，避免「金魚草」含「魚」被誤判為漁貨）
    "金魚草","玫瑰","菊花","百合","唐菖蒲","劍蘭","非洲菊","文心蘭","石斛蘭","蝴蝶蘭",
    "鬱金香","桔梗","洋桔梗","康乃馨","大理花","向日葵","滿天星","千日紅","火鶴","天堂鳥",
    "聖誕紅","虎頭蘭","報歲蘭","晚香玉","星辰花","嘉德麗雅","鳶尾",
    "薑荷花","荷花薑","火炬薑",  # 薑科花卉，含「薑」須優先排除避免誤判為蔬菜
]
SEAFOOD_KW = ["魚","蝦","蟹","蟳","蚵","牡蠣","蛤","鱸","虱目","吳郭","鮪","烏魚","帶魚",
              "鯖","鯧","鱲","魽","鰱","透抽","花枝","龍蝦","小卷","萬引",
              "鬼頭刀","鰹","海鱺","土魠","白帶魚","秋刀魚","鯛","黑鯛","石斑",  # 常見漁貨補充
             ]

# ── API 品名 → 顯示關鍵字 反向對照表（對應 MarketPriceService.apiNameAliases）──
# 農業部 API 品名（如「葉用甘藷」）→ App 顯示名稱（如「地瓜葉」）
API_ALIAS: dict[str, list[str]] = {
    "地瓜葉": ["葉用甘薯", "葉用甘藷", "甘薯葉", "甘藷葉", "地瓜葉", "番薯葉"],
    "小黃瓜": ["小黃瓜", "胡瓜"],
    "空心菜": ["空心菜", "蕹菜"],    # 蕹菜 → 顯示為空心菜；移除重複 key 避免後者覆蓋前者
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
    "山藥":   ["薯蕷", "山藥", "淮山", "長山藥", "日本山藥"],  # 薯蕷=API正確名稱
    "蓮藕":   ["蓮藕", "藕"],
    "蘆筍":   ["蘆筍", "石刁柏"],
    "菱角":   ["菱角", "菱"],
    "馬鈴薯": ["馬鈴薯", "洋芋", "土豆"],
    "地瓜":   ["甘薯", "甘藷", "地瓜", "番薯"],   # 甘薯=API正確名稱（薯不藷），顯示為「地瓜」
    "柳丁":     ["柳丁", "柳橙", "甜橙"],           # 柳丁=台灣市場慣用，柳橙=通稱
    "皇帝豆":  ["萊豆", "皇帝豆", "白扁豆"],       # 萊豆=農業部品名
    "瓠瓜":    ["扁蒲", "瓠瓜", "葫蘆"],           # 扁蒲=台灣市場慣用名
    "甜菜根":  ["甜菜根", "甜菜", "紅甜菜"],
    "胡蘿蔔":  ["胡蘿蔔", "紅蘿蔔"],               # 紅蘿蔔=部分市場慣稱
    "釋迦":    ["釋迦", "番荔枝", "鳳梨釋迦", "鳳梨番荔枝"],  # 含鳳梨釋迦（同為番荔枝品種）
    "鳳梨":    ["旺來", "金鑽鳳梨", "蜜寶鳳梨", "土鳳梨"],  # 旺來=台語鳳梨（農業部常見品名）；「鳳梨」本身由 FRUIT_KW 直接歸類，alias 只需涵蓋異名
    "梨子":    ["梨"],                              # 農業部品名含品種如「梨-幸水梨」
    "芭樂":    ["芭樂", "番石榴"],
    "百香果":  ["百香果", "西番蓮"],
    "蓮霧":    ["蓮霧"],  # 使「蓮霧-子彈型、巴掌蓮霧、紅蓮霧、翠玉、黑糖芭比」等品種均正規化為「蓮霧」
    # 蔬菜補充
    # ⚠️ 注意：「甘藷」key 已移除。其 alias 與「地瓜」完全重疊，
    #    留著會讓 _REVERSE_ALIAS["甘薯"]、["地瓜"] 被覆蓋成「甘藷」，
    #    導致 normalize_name 回傳「甘藷」而非「地瓜」，iOS 端查無記錄。
    "萵苣菜":  ["萵苣", "A菜", "福山萵苣", "蘿蔓萵苣", "萵苣菜"],
    "香菜":    ["香菜", "芫荽"],
    # 漁貨補充
    "鯖魚":    ["鯖魚", "白腹鯖", "花腹鯖"],
    "鮪魚":    ["鮪魚", "黑鮪", "黃鰭鮪", "鮪"],
    "小卷":    ["小卷", "鎖管"],
    "午仔魚":  ["午仔魚", "四指馬鮁", "午仔"],
    "飛魚":    ["飛魚", "飛烏"],
    "石蟳":    ["石蟳", "善泳蟳"],
    "紅蟳":    ["紅蟳", "擬深穴青蟳", "青蟳"],
    "鱸魚":    ["金目鱸", "加州鱸", "七星鱸", "鱸魚"],  # 農業部品名依品種列，統一正規化為「鱸魚」
    "草蝦":    ["草蝦"],                                  # 確保補查結果正規化一致
    "櫻桃蘿蔔": ["蘿蔔-櫻桃", "櫻桃蘿蔔"],                  # 農業部品名格式：蘿蔔-櫻桃；補查後 CropName 為「櫻桃蘿蔔」，加入自身確保 normalize_name 最長匹配勝過 "蘿蔔"→白蘿蔔
}
# 建立反向查表：API品名片段 → 顯示關鍵字
_REVERSE_ALIAS: dict[str, str] = {}
for display, api_names in API_ALIAS.items():
    for api_name in api_names:
        _REVERSE_ALIAS[api_name] = display

def normalize_name(crop_name: str) -> str:
    """將 API 回傳品名正規化為 App 顯示關鍵字，取最長匹配避免子字串誤判"""
    matches = [(api_name, display) for api_name, display in _REVERSE_ALIAS.items()
               if api_name in crop_name]
    if not matches:
        return crop_name
    # 取最長 api_name，例：「葉用甘藷」優先於「甘藷」，避免誤判為「地瓜」
    return max(matches, key=lambda x: len(x[0]))[1]

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
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
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

def fetch_all_agri(lookback: int = 7) -> list[dict]:
    """累積 lookback 天的農糧署行情，確保休市日或少量品項仍有 7 天均價可算"""
    all_records: list[dict] = []
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
        all_records.extend(records)
    return all_records

# 全量抓取不穩定的品名，需指定 CropName 補查
# 格式：(顯示名稱, [候選API品名, ...])  — 按順序試，取第一個有真實成交的
SUPPLEMENT_QUERIES: list[tuple[str, list[str], int]] = [
    # (顯示名稱, [候選API品名], 回溯天數)
    # 注意：API 用字是「甘薯」（薯），不是「甘藷」（藷）
    # 地瓜葉別名：農業部品名有「甘薯葉」「葉用甘藷」「葉用甘薯」三種變體
    ("地瓜葉", ["甘薯葉", "葉用甘藷", "葉用甘薯"], 60),
    ("地瓜",   ["甘薯", "甘藷", "番薯"],           60),
    ("莧菜",   ["莧菜"],                            30),
    ("龍鬚菜", ["龍鬚菜"],                          30),
    ("蘆筍",   ["蘆筍", "石刁柏"],                  30),
    ("山藥",   ["薯蕷", "山藥", "淮山"],            90),  # 薯蕷=API正確名稱，季節性品項
    # 季節性品項（冬季盛產，夏季無貨，加長回溯取最近一季均價）
    ("柳丁",    ["柳丁", "柳橙", "甜橙"],           180),  # 冬季水果 11~3月
    ("皇帝豆",  ["萊豆", "皇帝豆", "白扁豆"],       180),  # 冬季豆類 10~3月
    ("瓠瓜",    ["扁蒲", "瓠瓜", "葫蘆"],           180),  # 部分市場稱扁蒲，夏冬皆有但行情不穩
    ("甜菜根",  ["甜菜根", "甜菜", "紅甜菜"],       365),  # 非主流蔬菜，年度回溯
    ("釋迦",    ["釋迦", "番荔枝", "鳳梨釋迦", "鳳梨番荔枝"],  180),  # 含鳳梨釋迦（同為番荔枝品種）；冬季 9~3月
    ("胡蘿蔔",  ["胡蘿蔔", "紅蘿蔔"],               90),  # 行情資料較少，補查確保覆蓋
    ("梨子",    ["梨"],                              60),  # 全量抓取可能漏掉，補查確保
    ("鳳梨",    ["旺來", "鳳梨", "金鑽鳳梨", "土鳳梨", "蜜寶鳳梨"],  30),  # 旺來=台語品名；農業部 API 品名多樣，廣撒確保覆蓋
    # 夏季高需求品項（6-9月）— 市場主流，但偶爾批次抓不到
    ("番茄",    ["番茄", "小番茄", "聖女番茄"],      30),
    ("玉米",    ["玉米", "甜玉米", "糯玉米"],         30),
    ("芒果",    ["芒果", "金煌芒果", "愛文芒果"],    60),  # 台灣夏季最重要水果
    ("荔枝",    ["荔枝"],                             60),  # 6-7月盛產
    ("龍眼",    ["龍眼"],                             60),  # 7-9月盛產
    # 大暑/立秋節氣食材（全量批次抓取常因季節性或品項小眾而遺漏）
    ("草蝦",    ["草蝦"],                              60),  # 夏季漁貨；農糧署養殖魚市也有收錄
    ("鱸魚",    ["金目鱸", "加州鱸", "七星鱸", "鱸魚"], 60),  # 農業部依品種分列，統一補查
    ("金針",    ["金針", "金針花"],                    60),  # 黃花菜，6-8月盛產
    ("小卷",    ["鎖管", "小卷"],                      60),  # 漁業署品名為「鎖管」，季節性漁貨
    ("櫻桃蘿蔔", ["蘿蔔-櫻桃"],                          90),  # 農業部品名格式：蘿蔔-櫻桃
]

def fetch_agri_by_name(display_name: str, candidates: list[str], lookback: int = 30) -> list[dict]:
    """嘗試多個 API 品名，回傳第一組有真實成交的資料（過濾掉休市佔位記錄）"""
    start_date = roc_date(lookback - 1)
    end_date   = roc_date(0)
    for crop_name in candidates:
        params = urllib.parse.urlencode({
            "Start_time": start_date,
            "End_time":   end_date,
            "CropName":   crop_name,
        })
        data = fetch_json(f"{AGRI_BASE}?{params}")
        if not data:
            continue
        raw = data.get("Data") or []
        # 先以原始 CropName 過濾休市，再覆寫為 display_name
        real = [r for r in raw
                if r.get("CropName", "") not in ("休市", "-", "")
                and parse_float(r.get("Avg_Price", 0)) > 0]
        print(f"      [{start_date}~{end_date}] {crop_name}: {len(raw)} 筆原始 → {len(real)} 筆有效")
        if real:
            for r in real:
                r["CropName"] = display_name
            return real
    print(f"      ⚠ {display_name}：候選品名 {candidates} 均無成交資料（{start_date}~{end_date}）")
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
    if not crop or crop in ("休市", "-", ""):
        return None
    cat  = classify(crop)
    if cat is None:
        return None
    date         = r.get("TransDate", "")
    market       = r.get("MarketName", "")
    high         = parse_float(r.get("Upper_Price", 0))
    mid          = parse_float(r.get("Middle_Price", 0))
    low          = parse_float(r.get("Lower_Price", 0))
    avg          = parse_float(r.get("Avg_Price", 0))
    # 農業部對少量交易品項常不填中間價，依序 fallback
    if mid <= 0:
        if avg > 0:
            mid = avg
        elif high > 0 and low > 0:
            mid = round((high + low) / 2, 1)
        elif high > 0:
            mid = high
        else:
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

def fetch_all_aquatic(lookback: int = 14) -> list[dict]:
    """累積 lookback 天的漁業署行情，確保休市日或少量品項仍有 14 天均價可算"""
    all_records: list[dict] = []
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
        all_records.extend(records)
    return all_records

def aquatic_to_price(r: dict) -> dict | None:
    fish_name = r.get("魚貨名稱", "")
    if not fish_name or fish_name in ("休市", "-", ""):
        return None
    # 排除花卉品名（如「金魚草」，漁業署資料偶有錯誤分類）
    if any(kw in fish_name for kw in FLOWER_KW):
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
    for display_name, candidates, lookback in SUPPLEMENT_QUERIES:
        if display_name not in seen_display:
            extra = fetch_agri_by_name(display_name, candidates, lookback)
            if extra:
                print(f"    {display_name} → {len(extra)} 筆")
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

    # 防護：總筆數為 0 → API 全數失敗
    if not all_prices:
        print("\n❌ 本次抓取 0 筆有效行情，疑似 API 全數逾時或停服。")
        print("   中止寫出，保留 docs/prices.json 舊版資料。")
        import sys; sys.exit(1)

    # 防護：農業部農糧署 API 部分失敗時，蔬菜或水果筆數會異常偏低
    # 正常情況：蔬菜 ≥ 200 筆、水果 ≥ 50 筆；低於此值表示農業部 API 逾時，不覆蓋舊版
    veg_count   = cats.get("蔬菜", 0)
    fruit_count = cats.get("水果", 0)
    if veg_count < 200:
        print(f"\n❌ 蔬菜僅 {veg_count} 筆（閾值 200），農業部農糧署 API 疑似逾時。")
        print("   中止寫出，保留 docs/prices.json 舊版資料。")
        import sys; sys.exit(1)
    if fruit_count < 50:
        print(f"\n❌ 水果僅 {fruit_count} 筆（閾值 50），農業部農糧署 API 疑似逾時。")
        print("   中止寫出，保留 docs/prices.json 舊版資料。")
        import sys; sys.exit(1)

    # 寫出 JSON
    import os
    # 使用腳本絕對路徑（與 push_prices.py 一致），避免 cwd 不同導致寫錯位置
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _DOCS_DIR   = os.path.join(_SCRIPT_DIR, "..", "docs")
    os.makedirs(_DOCS_DIR, exist_ok=True)
    meta = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count":     len(all_prices),
        "prices":    all_prices,
    }
    out_path = os.path.join(_DOCS_DIR, "prices.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n💾 已寫入 {out_path}")

if __name__ == "__main__":
    main()
