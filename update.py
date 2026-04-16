#!/usr/bin/env python3
"""Fetch stock data from Yahoo Finance and write data.json for the dashboard."""
import json
import urllib.request
import urllib.parse
from datetime import datetime

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
    # Watchlist
    "C6L.SI":  "SIA",
    "U11.SI":  "UOB",
    "D05.SI":  "DBS",
    "O39.SI":  "OCBC",
    "HST":     "HST",
    "BBY":     "BBY",
    "NET":     "NET",
    "T":       "T",
    "MSFT":    "MSFT",
    "AMZN":    "AMZN",
    "NOW":     "NOW",
    "NFLX":    "NFLX",
    "UNH":     "UNH",
    "BBAI":    "BBAI",
    "INTC":    "INTC",
    "NKE":     "NKE",
    "HPQ":     "HPQ",
    "PFE":     "PFE",
    "PLTR":    "PLTR",
    "SPY":     "SPY",
}


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
    """Fetch the all-time high price using max available history."""
    url = f"{YAHOO_BASE}/{urllib.parse.quote(yahoo_symbol)}?interval=1mo&range=max"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    result = data["chart"]["result"][0]
    highs = result["indicators"]["quote"][0].get("high", [])
    valid = [h for h in highs if h is not None]
    if not valid:
        return None
    return round(max(valid), 2)


def main():
    results = {}
    for yahoo_sym, label in SYMBOLS.items():
        try:
            q = fetch_quote(yahoo_sym)
            # Fetch ATH from max history
            try:
                ath = fetch_ath(yahoo_sym)
                q["ath"] = ath
            except Exception as e2:
                print(f"  ⚠ {label:6s}  ATH fetch failed – {e2}")
                q["ath"] = None
            results[yahoo_sym] = q
            sign = "+" if (q["change"] or 0) >= 0 else ""
            ath_str = f"  ATH: {q['ath']}" if q.get("ath") else ""
            print(f"  ✓ {label:6s}  {q['price']:>12.2f}  {sign}{q.get('change', 0) or 0:.2f}{ath_str}")
        except Exception as e:
            print(f"  ✗ {label:6s}  FAILED – {e}")
            results[yahoo_sym] = None

    out = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": results,
    }
    with open("data.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n✓ data.json written ({len(results)} symbols)")


if __name__ == "__main__":
    main()
