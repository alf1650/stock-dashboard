#!/usr/bin/env python3
"""Fetch stock data from Yahoo Finance and write data.json for the dashboard."""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

SYMBOLS = {
    # Indices
    "^VIX":    "VIX",
    "^DJI":    "DJI",
    "^NDX":    "NDX",
    "^GSPC":   "SPX",
    "^RUT":    "RUT",
    "VWRA.L":  "VWRA",
    "XNAS.L":  "XNAS",
    "USDSGD=X":"USDSGD",
}

# Top US tech-growth high-movement stocks (technical-analysis focus: SMA200 + period returns)
MOVERS = [
    "NVDA", "AMD", "TSLA", "PLTR", "META", "MSFT", "GOOGL", "AMZN",
    "AVGO", "CRWD", "SMCI", "MU", "ARM", "MRVL", "NFLX", "ORCL",
    "NOW", "SNOW", "COIN", "SHOP", "INTC", "LAC",
]


def fetch_quote(yahoo_symbol):
    """Fetch a single quote from Yahoo Finance v8 chart endpoint."""
    url = f"{YAHOO_BASE}/{urllib.parse.quote(yahoo_symbol)}?interval=1d&range=2d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta["regularMarketPrice"]
    closes = result["indicators"]["quote"][0].get("close", [])
    change = None
    change_pct = None
    if len(closes) >= 2 and closes[-2] is not None:
        prev = closes[-2]
        change = round(price - prev, 4)
        change_pct = round((price - prev) / prev * 100, 4)
    return {
        "price": price,
        "change": change,
        "changePct": change_pct,
        "high52": meta.get("fiftyTwoWeekHigh"),
        "low52": meta.get("fiftyTwoWeekLow"),
        "volume": meta.get("regularMarketVolume"),
        "currency": meta.get("currency"),
        "name": meta.get("longName") or meta.get("shortName"),
    }


def fetch_ath(yahoo_symbol):
    """Fetch the all-time high closing price and its date using max available daily history."""
    url = f"{YAHOO_BASE}/{urllib.parse.quote(yahoo_symbol)}?interval=1d&range=max"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    result = data["chart"]["result"][0]
    closes = result["indicators"]["quote"][0].get("close", [])
    timestamps = result.get("timestamp", [])
    best_price = None
    best_ts = None
    for i, c in enumerate(closes):
        if c is not None and (best_price is None or c > best_price):
            best_price = c
            best_ts = timestamps[i] if i < len(timestamps) else None
    if best_price is None:
        return None, None
    ath_date = datetime.fromtimestamp(best_ts, tz=timezone.utc).strftime("%Y-%m-%d") if best_ts else None
    return round(best_price, 2), ath_date


def fetch_mover(yahoo_symbol):
    """Fetch ~1y of daily history and compute SMA200 + period returns for a mover."""
    url = f"{YAHOO_BASE}/{urllib.parse.quote(yahoo_symbol)}?interval=1d&range=1y"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    result = data["chart"]["result"][0]
    meta = result["meta"]
    closes_raw = result["indicators"]["quote"][0].get("close", [])
    # Filter out None entries (non-trading days etc) keeping order
    closes = [c for c in closes_raw if c is not None]
    if len(closes) < 2:
        raise ValueError("insufficient history")

    price = meta.get("regularMarketPrice") or closes[-1]
    name = meta.get("longName") or meta.get("shortName") or yahoo_symbol

    def pct_back(n):
        if len(closes) <= n:
            return None
        ref = closes[-(n + 1)]
        if ref is None or ref == 0:
            return None
        return round((price - ref) / ref * 100, 2)

    daily_pct = pct_back(1)
    week1_pct = pct_back(5)
    week2_pct = pct_back(10)
    week4_pct = pct_back(20)

    sma200 = None
    if len(closes) >= 200:
        sma200 = round(sum(closes[-200:]) / 200, 2)
    elif len(closes) >= 50:
        # Fallback: use whatever we have so users still see a moving avg (label kept SMA200)
        sma200 = round(sum(closes) / len(closes), 2)

    vs_sma = None
    if sma200 and price:
        vs_sma = round((price - sma200) / sma200 * 100, 2)

    return {
        "name": name,
        "price": round(price, 2),
        "currency": meta.get("currency"),
        "dailyPct": daily_pct,
        "week1Pct": week1_pct,
        "week2Pct": week2_pct,
        "week4Pct": week4_pct,
        "sma200": sma200,
        "vsSma200Pct": vs_sma,
        "high52": meta.get("fiftyTwoWeekHigh"),
        "low52": meta.get("fiftyTwoWeekLow"),
    }


def main():
    results = {}
    for yahoo_sym, label in SYMBOLS.items():
        try:
            q = fetch_quote(yahoo_sym)
            # Fetch ATH from max history
            try:
                ath, ath_date = fetch_ath(yahoo_sym)
                q["ath"] = ath
                q["athDate"] = ath_date
            except Exception as e2:
                print(f"  ⚠ {label:6s}  ATH fetch failed – {e2}")
                q["ath"] = None
                q["athDate"] = None
            results[yahoo_sym] = q
            sign = "+" if (q["change"] or 0) >= 0 else ""
            ath_str = f"  ATH: {q['ath']}" if q.get("ath") else ""
            print(f"  ✓ {label:6s}  {q['price']:>12.2f}  {sign}{q.get('change', 0) or 0:.2f}{ath_str}")
        except Exception as e:
            print(f"  ✗ {label:6s}  FAILED – {e}")
            results[yahoo_sym] = None

    movers = {}
    print("\n--- Movers (1y history, SMA200 + period returns) ---")
    for sym in MOVERS:
        try:
            m = fetch_mover(sym)
            movers[sym] = m
            print(f"  ✓ {sym:6s}  {m['price']:>10.2f}  d:{m['dailyPct'] or 0:+6.2f}%  "
                  f"1w:{m['week1Pct'] or 0:+6.2f}%  4w:{m['week4Pct'] or 0:+6.2f}%  "
                  f"SMA200:{m['sma200'] or 0:>10.2f}  vs:{m['vsSma200Pct'] or 0:+6.2f}%")
        except Exception as e:
            print(f"  ✗ {sym:6s}  FAILED – {e}")
            movers[sym] = None

    out = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": results,
        "movers": movers,
    }
    with open("data.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n✓ data.json written ({len(results)} symbols, {len(movers)} movers)")


if __name__ == "__main__":
    main()
