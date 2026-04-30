import asyncio
import yfinance as yf
from datetime import datetime
import sys
import logging

logger = logging.getLogger('yfinance')
logger.disabled = True
logger.propagate = False

async def fetch_single_asset(name: str, symbol: str, fallback_currency: str) -> dict:
    """
    Runs the blocking yfinance network call in a separate thread.
    Returns a standardized dictionary containing either the price or an error state.
    """
    def _sync_fetch():
        
        ticker = yf.Ticker(symbol)
      
        hist = ticker.history(period="1d")
        
        if hist.empty:
            raise ValueError("No pricing data returned from API.")
        
        price = float(hist['Close'].iloc[-1])
        currency = ticker.info.get('currency', fallback_currency)
        
        return price, currency

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        
        price, currency = await asyncio.to_thread(_sync_fetch)
        
        return {
            "name": name,
            "symbol": symbol,
            "price": price,
            "currency": currency,
            "timestamp": timestamp,
            "error": None
        }
    except Exception as e:
       
        return {
            "name": name,
            "symbol": symbol,
            "price": None,
            "currency": "---",
            "timestamp": timestamp,
            "error": "Symbol not found or delisted" # Clean, safe error message
        }

async def main():
    # 1. Define the assets (Stock Index, NSE Stock, Crypto, and one deliberate error)
    assets = [
        {"name": "NIFTY 50", "symbol": "^NSEI", "fallback_currency": "INR"},
        {"name": "Reliance Ind.", "symbol": "RELIANCE.NS", "fallback_currency": "INR"},
        {"name": "Fake Coin (Error)", "symbol": "INVALID_XYZ", "fallback_currency": "USD"},
        {"name": "Bitcoin", "symbol": "BTC-USD", "fallback_currency": "USD"},
        {"name": "Fake Coin (Error)", "symbol": "INVALID_XYZ", "fallback_currency": "USD"}
    ]

    # 2. Print Table Header
    print("\n" + "=" * 80)
    print("ASYNC MARKET DATA ENGINE")
    print("=" * 80)
    print(f"{'Asset Name':<25} | {'Current Price':>15} | {'Currency':<8} | {'Timestamp'}")
    print("-" * 80)

    # 3. Fire all network requests concurrently
    tasks = [fetch_single_asset(a["name"], a["symbol"], a["fallback_currency"]) for a in assets]
    results = await asyncio.gather(*tasks)

    # 4. Process and format the results
    for res in results:
        if res["error"] is None:
            # Success row
            print(f"{res['name']:<25} | {res['price']:>15.2f} | {res['currency']:<8} | {res['timestamp']}")
        else:
            # Graceful failure row
            print(f"{res['name']:<25} | {'FETCH FAILED':>15} | {res['currency']:<8} | {res['timestamp']}")
            # Log the error cleanly
            print(f"   -> [Log] {res['symbol']}: {res['error']}", file=sys.stderr)

    print("=" * 80 + "\n")

if __name__ == "__main__":
    asyncio.run(main())