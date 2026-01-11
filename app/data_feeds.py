"""
================================================================================
                    GOLDBACH DATA FEEDS MODULE
                    Multiple Data Provider Integrations
================================================================================

Поддържани providers:
- TradingView Webhooks (real-time alerts)
- Yahoo Finance (free, delayed)
- Twelve Data API (real-time, free tier)
- Alpha Vantage (free tier)
- Polygon.io (stocks/forex)
- MetaTrader 5 (via API)

================================================================================
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import threading
from queue import Queue
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================================
#                              DATA CLASSES
# ==============================================================================

@dataclass
class PriceData:
    """Стандартизирана ценова информация."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    source: str = "unknown"
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source
        }


@dataclass
class DataFeedConfig:
    """Конфигурация за data feed."""
    provider: str
    api_key: str = ""
    symbols: List[str] = field(default_factory=list)
    interval: str = "1d"  # 1m, 5m, 15m, 1h, 4h, 1d
    auto_refresh: bool = True
    refresh_seconds: int = 60


# ==============================================================================
#                              BASE PROVIDER
# ==============================================================================

class DataProvider(ABC):
    """Abstract base class за data providers."""
    
    def __init__(self, config: DataFeedConfig):
        self.config = config
        self.last_prices: Dict[str, PriceData] = {}
        self.callbacks: List[Callable[[PriceData], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    @abstractmethod
    def fetch_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price for symbol."""
        pass
    
    @abstractmethod
    def fetch_history(self, symbol: str, days: int = 100) -> List[PriceData]:
        """Fetch historical data."""
        pass
    
    def on_price_update(self, callback: Callable[[PriceData], None]):
        """Register callback for price updates."""
        self.callbacks.append(callback)
    
    def _notify_callbacks(self, price: PriceData):
        """Notify all callbacks of price update."""
        for callback in self.callbacks:
            try:
                callback(price)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def start_auto_refresh(self):
        """Start automatic price refresh in background."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()
        logger.info(f"Started auto-refresh for {self.config.provider}")
    
    def stop_auto_refresh(self):
        """Stop automatic refresh."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _refresh_loop(self):
        """Background refresh loop."""
        while self._running:
            for symbol in self.config.symbols:
                try:
                    price = self.fetch_price(symbol)
                    if price:
                        self.last_prices[symbol] = price
                        self._notify_callbacks(price)
                except Exception as e:
                    logger.error(f"Refresh error for {symbol}: {e}")
            
            time.sleep(self.config.refresh_seconds)


# ==============================================================================
#                              YAHOO FINANCE
# ==============================================================================

class YahooFinanceProvider(DataProvider):
    """
    Yahoo Finance data provider.
    Free, no API key needed, but has rate limits.
    """
    
    SYMBOL_MAP = {
        # Futures
        "NQ": "NQ=F",
        "ES": "ES=F",
        "YM": "YM=F",
        "RTY": "RTY=F",
        "GC": "GC=F",
        "SI": "SI=F",
        "CL": "CL=F",
        # Forex
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "XAUUSD": "GC=F",
        # Crypto
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
    }
    
    def _get_yahoo_symbol(self, symbol: str) -> str:
        """Convert symbol to Yahoo format."""
        return self.SYMBOL_MAP.get(symbol.upper(), symbol)
    
    def fetch_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price from Yahoo Finance."""
        try:
            import yfinance as yf
            
            yahoo_symbol = self._get_yahoo_symbol(symbol)
            ticker = yf.Ticker(yahoo_symbol)
            
            # Get latest data
            hist = ticker.history(period="1d", interval="1m")
            if hist.empty:
                hist = ticker.history(period="5d", interval="1d")
            
            if hist.empty:
                return None
            
            latest = hist.iloc[-1]
            
            return PriceData(
                symbol=symbol,
                timestamp=datetime.now(),
                open=float(latest['Open']),
                high=float(latest['High']),
                low=float(latest['Low']),
                close=float(latest['Close']),
                volume=float(latest.get('Volume', 0)),
                source="yahoo"
            )
        except Exception as e:
            logger.error(f"Yahoo fetch error: {e}")
            return None
    
    def fetch_history(self, symbol: str, days: int = 100) -> List[PriceData]:
        """Fetch historical data from Yahoo Finance."""
        try:
            import yfinance as yf
            
            yahoo_symbol = self._get_yahoo_symbol(symbol)
            ticker = yf.Ticker(yahoo_symbol)
            
            # Map interval
            interval_map = {
                "1m": "1m", "5m": "5m", "15m": "15m",
                "1h": "1h", "4h": "1h", "1d": "1d"
            }
            yf_interval = interval_map.get(self.config.interval, "1d")
            
            # Fetch data
            hist = ticker.history(period=f"{days}d", interval=yf_interval)
            
            result = []
            for idx, row in hist.iterrows():
                result.append(PriceData(
                    symbol=symbol,
                    timestamp=idx.to_pydatetime(),
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=float(row.get('Volume', 0)),
                    source="yahoo"
                ))
            
            return result
        except Exception as e:
            logger.error(f"Yahoo history error: {e}")
            return []


# ==============================================================================
#                              TWELVE DATA
# ==============================================================================

class TwelveDataProvider(DataProvider):
    """
    Twelve Data API provider.
    Free tier: 800 API calls/day, 8 calls/minute.
    Real-time data available.
    
    Sign up: https://twelvedata.com/
    """
    
    BASE_URL = "https://api.twelvedata.com"
    
    def fetch_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price from Twelve Data."""
        try:
            url = f"{self.BASE_URL}/price"
            params = {
                "symbol": symbol,
                "apikey": self.config.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if "price" not in data:
                logger.error(f"Twelve Data error: {data}")
                return None
            
            # For full OHLC, use time_series
            return self._fetch_latest_bar(symbol)
            
        except Exception as e:
            logger.error(f"Twelve Data fetch error: {e}")
            return None
    
    def _fetch_latest_bar(self, symbol: str) -> Optional[PriceData]:
        """Fetch latest OHLC bar."""
        try:
            url = f"{self.BASE_URL}/time_series"
            params = {
                "symbol": symbol,
                "interval": self.config.interval,
                "outputsize": 1,
                "apikey": self.config.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if "values" not in data or not data["values"]:
                return None
            
            bar = data["values"][0]
            
            return PriceData(
                symbol=symbol,
                timestamp=datetime.fromisoformat(bar["datetime"]),
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                volume=float(bar.get("volume", 0)),
                source="twelvedata"
            )
        except Exception as e:
            logger.error(f"Twelve Data bar error: {e}")
            return None
    
    def fetch_history(self, symbol: str, days: int = 100) -> List[PriceData]:
        """Fetch historical data from Twelve Data."""
        try:
            url = f"{self.BASE_URL}/time_series"
            params = {
                "symbol": symbol,
                "interval": self.config.interval,
                "outputsize": min(days * 24, 5000),  # Max 5000
                "apikey": self.config.api_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if "values" not in data:
                logger.error(f"Twelve Data history error: {data}")
                return []
            
            result = []
            for bar in reversed(data["values"]):  # Oldest first
                result.append(PriceData(
                    symbol=symbol,
                    timestamp=datetime.fromisoformat(bar["datetime"]),
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=float(bar.get("volume", 0)),
                    source="twelvedata"
                ))
            
            return result
        except Exception as e:
            logger.error(f"Twelve Data history error: {e}")
            return []


# ==============================================================================
#                              ALPHA VANTAGE
# ==============================================================================

class AlphaVantageProvider(DataProvider):
    """
    Alpha Vantage API provider.
    Free tier: 25 API calls/day.
    
    Sign up: https://www.alphavantage.co/support/#api-key
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def fetch_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price from Alpha Vantage."""
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.config.api_key
            }
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            data = response.json()
            
            if "Global Quote" not in data:
                logger.error(f"Alpha Vantage error: {data}")
                return None
            
            quote = data["Global Quote"]
            
            return PriceData(
                symbol=symbol,
                timestamp=datetime.now(),
                open=float(quote.get("02. open", 0)),
                high=float(quote.get("03. high", 0)),
                low=float(quote.get("04. low", 0)),
                close=float(quote.get("05. price", 0)),
                volume=float(quote.get("06. volume", 0)),
                source="alphavantage"
            )
        except Exception as e:
            logger.error(f"Alpha Vantage fetch error: {e}")
            return None
    
    def fetch_history(self, symbol: str, days: int = 100) -> List[PriceData]:
        """Fetch historical data from Alpha Vantage."""
        try:
            # Map interval to function
            if self.config.interval in ["1m", "5m", "15m", "30m", "1h"]:
                function = "TIME_SERIES_INTRADAY"
                interval_param = {"interval": self.config.interval.replace("m", "min").replace("h", "0min")}
            else:
                function = "TIME_SERIES_DAILY"
                interval_param = {}
            
            params = {
                "function": function,
                "symbol": symbol,
                "outputsize": "full" if days > 100 else "compact",
                "apikey": self.config.api_key,
                **interval_param
            }
            
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            data = response.json()
            
            # Find time series key
            ts_key = None
            for key in data.keys():
                if "Time Series" in key:
                    ts_key = key
                    break
            
            if not ts_key:
                logger.error(f"Alpha Vantage history error: {data}")
                return []
            
            result = []
            for dt_str, bar in list(data[ts_key].items())[:days]:
                result.append(PriceData(
                    symbol=symbol,
                    timestamp=datetime.fromisoformat(dt_str),
                    open=float(bar.get("1. open", 0)),
                    high=float(bar.get("2. high", 0)),
                    low=float(bar.get("3. low", 0)),
                    close=float(bar.get("4. close", 0)),
                    volume=float(bar.get("5. volume", 0)),
                    source="alphavantage"
                ))
            
            return list(reversed(result))  # Oldest first
        except Exception as e:
            logger.error(f"Alpha Vantage history error: {e}")
            return []


# ==============================================================================
#                              POLYGON.IO
# ==============================================================================

class PolygonProvider(DataProvider):
    """
    Polygon.io API provider.
    Free tier: 5 API calls/minute for stocks.
    
    Sign up: https://polygon.io/
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def fetch_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price from Polygon."""
        try:
            # Determine if forex or stock
            if "/" in symbol or symbol.startswith("C:"):
                return self._fetch_forex(symbol)
            else:
                return self._fetch_stock(symbol)
        except Exception as e:
            logger.error(f"Polygon fetch error: {e}")
            return None
    
    def _fetch_stock(self, symbol: str) -> Optional[PriceData]:
        """Fetch stock price."""
        url = f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/prev"
        params = {"apiKey": self.config.api_key}
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("resultsCount", 0) == 0:
            return None
        
        bar = data["results"][0]
        
        return PriceData(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(bar["t"] / 1000),
            open=float(bar["o"]),
            high=float(bar["h"]),
            low=float(bar["l"]),
            close=float(bar["c"]),
            volume=float(bar.get("v", 0)),
            source="polygon"
        )
    
    def _fetch_forex(self, symbol: str) -> Optional[PriceData]:
        """Fetch forex price."""
        # Convert EURUSD to C:EURUSD format
        if not symbol.startswith("C:"):
            symbol = f"C:{symbol.replace('/', '')}"
        
        url = f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/prev"
        params = {"apiKey": self.config.api_key}
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("resultsCount", 0) == 0:
            return None
        
        bar = data["results"][0]
        
        return PriceData(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(bar["t"] / 1000),
            open=float(bar["o"]),
            high=float(bar["h"]),
            low=float(bar["l"]),
            close=float(bar["c"]),
            volume=float(bar.get("v", 0)),
            source="polygon"
        )
    
    def fetch_history(self, symbol: str, days: int = 100) -> List[PriceData]:
        """Fetch historical data from Polygon."""
        try:
            # Map interval
            multiplier = 1
            timespan = "day"
            if self.config.interval == "1m":
                timespan = "minute"
            elif self.config.interval == "5m":
                multiplier = 5
                timespan = "minute"
            elif self.config.interval == "15m":
                multiplier = 15
                timespan = "minute"
            elif self.config.interval == "1h":
                timespan = "hour"
            elif self.config.interval == "4h":
                multiplier = 4
                timespan = "hour"
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            url = f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            params = {"apiKey": self.config.api_key, "limit": 50000}
            
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if "results" not in data:
                return []
            
            result = []
            for bar in data["results"]:
                result.append(PriceData(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(bar["t"] / 1000),
                    open=float(bar["o"]),
                    high=float(bar["h"]),
                    low=float(bar["l"]),
                    close=float(bar["c"]),
                    volume=float(bar.get("v", 0)),
                    source="polygon"
                ))
            
            return result
        except Exception as e:
            logger.error(f"Polygon history error: {e}")
            return []


# ==============================================================================
#                              TRADINGVIEW WEBHOOKS
# ==============================================================================

class TradingViewWebhook:
    """
    Handler for TradingView webhook alerts.
    
    Setup in TradingView:
    1. Create Alert on any indicator/strategy
    2. Set Webhook URL: https://your-domain.com/api/webhook/tradingview
    3. Set Message format (JSON):
       {
           "symbol": "{{ticker}}",
           "price": {{close}},
           "action": "{{strategy.order.action}}",
           "time": "{{time}}"
       }
    """
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key
        self.callbacks: List[Callable[[Dict], None]] = []
        self.last_alert: Optional[Dict] = None
    
    def on_alert(self, callback: Callable[[Dict], None]):
        """Register callback for alerts."""
        self.callbacks.append(callback)
    
    def process_webhook(self, data: Dict, headers: Dict = None) -> bool:
        """
        Process incoming webhook from TradingView.
        
        Args:
            data: Webhook payload
            headers: Request headers for validation
            
        Returns:
            True if processed successfully
        """
        # Validate secret if configured
        if self.secret_key:
            received_key = headers.get("X-TV-Secret") if headers else None
            if received_key != self.secret_key:
                logger.warning("Invalid TradingView webhook secret")
                return False
        
        # Parse and normalize data
        try:
            alert = {
                "symbol": data.get("symbol", "UNKNOWN"),
                "price": float(data.get("price", data.get("close", 0))),
                "action": data.get("action", ""),
                "time": data.get("time", datetime.now().isoformat()),
                "raw": data
            }
            
            self.last_alert = alert
            
            # Notify callbacks
            for callback in self.callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"TradingView callback error: {e}")
            
            logger.info(f"Processed TradingView alert: {alert['symbol']} @ {alert['price']}")
            return True
            
        except Exception as e:
            logger.error(f"TradingView webhook error: {e}")
            return False


# ==============================================================================
#                              DATA FEED MANAGER
# ==============================================================================

class DataFeedManager:
    """
    Централен мениджър за всички data feeds.
    
    Поддържа multiple providers едновременно с fallback.
    """
    
    PROVIDERS = {
        "yahoo": YahooFinanceProvider,
        "twelvedata": TwelveDataProvider,
        "alphavantage": AlphaVantageProvider,
        "polygon": PolygonProvider,
    }
    
    def __init__(self):
        self.providers: Dict[str, DataProvider] = {}
        self.primary_provider: Optional[str] = None
        self.tradingview = TradingViewWebhook()
        self.price_cache: Dict[str, PriceData] = {}
        self.callbacks: List[Callable[[PriceData], None]] = []
    
    def add_provider(self, name: str, config: DataFeedConfig) -> bool:
        """Add a data provider."""
        provider_class = self.PROVIDERS.get(config.provider.lower())
        if not provider_class:
            logger.error(f"Unknown provider: {config.provider}")
            return False
        
        provider = provider_class(config)
        provider.on_price_update(self._on_price_update)
        self.providers[name] = provider
        
        if not self.primary_provider:
            self.primary_provider = name
        
        logger.info(f"Added provider: {name} ({config.provider})")
        return True
    
    def set_primary(self, name: str):
        """Set primary provider."""
        if name in self.providers:
            self.primary_provider = name
    
    def on_price_update(self, callback: Callable[[PriceData], None]):
        """Register callback for price updates."""
        self.callbacks.append(callback)
    
    def _on_price_update(self, price: PriceData):
        """Internal price update handler."""
        self.price_cache[price.symbol] = price
        for callback in self.callbacks:
            try:
                callback(price)
            except Exception as e:
                logger.error(f"Price callback error: {e}")
    
    def get_price(self, symbol: str, provider: str = None) -> Optional[PriceData]:
        """Get current price for symbol."""
        provider_name = provider or self.primary_provider
        if not provider_name or provider_name not in self.providers:
            # Try all providers
            for name, prov in self.providers.items():
                price = prov.fetch_price(symbol)
                if price:
                    return price
            return None
        
        return self.providers[provider_name].fetch_price(symbol)
    
    def get_history(self, symbol: str, days: int = 100, 
                    provider: str = None) -> List[PriceData]:
        """Get historical data for symbol."""
        provider_name = provider or self.primary_provider
        if not provider_name or provider_name not in self.providers:
            return []
        
        return self.providers[provider_name].fetch_history(symbol, days)
    
    def start_all(self):
        """Start auto-refresh for all providers."""
        for name, provider in self.providers.items():
            if provider.config.auto_refresh:
                provider.start_auto_refresh()
    
    def stop_all(self):
        """Stop all providers."""
        for provider in self.providers.values():
            provider.stop_auto_refresh()
    
    def get_status(self) -> Dict:
        """Get status of all providers."""
        return {
            "providers": {
                name: {
                    "type": prov.config.provider,
                    "symbols": prov.config.symbols,
                    "running": prov._running,
                    "last_prices": {
                        sym: p.to_dict() for sym, p in prov.last_prices.items()
                    }
                }
                for name, prov in self.providers.items()
            },
            "primary": self.primary_provider,
            "cache_size": len(self.price_cache)
        }


# ==============================================================================
#                              GLOBAL INSTANCE
# ==============================================================================

data_manager = DataFeedManager()


# ==============================================================================
#                              FACTORY FUNCTIONS
# ==============================================================================

def create_yahoo_feed(symbols: List[str], interval: str = "1d", 
                      refresh_seconds: int = 60) -> DataFeedConfig:
    """Create Yahoo Finance feed config."""
    return DataFeedConfig(
        provider="yahoo",
        symbols=symbols,
        interval=interval,
        auto_refresh=True,
        refresh_seconds=refresh_seconds
    )


def create_twelvedata_feed(api_key: str, symbols: List[str], 
                           interval: str = "1day") -> DataFeedConfig:
    """Create Twelve Data feed config."""
    return DataFeedConfig(
        provider="twelvedata",
        api_key=api_key,
        symbols=symbols,
        interval=interval,
        auto_refresh=True,
        refresh_seconds=60
    )


def create_polygon_feed(api_key: str, symbols: List[str]) -> DataFeedConfig:
    """Create Polygon.io feed config."""
    return DataFeedConfig(
        provider="polygon",
        api_key=api_key,
        symbols=symbols,
        interval="1d",
        auto_refresh=True,
        refresh_seconds=60
    )


# ==============================================================================
#                              TEST
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  DATA FEEDS TEST")
    print("=" * 70)
    
    # Test Yahoo Finance (no API key needed)
    config = create_yahoo_feed(["NQ", "ES", "EURUSD"], interval="1d")
    manager = DataFeedManager()
    manager.add_provider("yahoo", config)
    
    # Fetch price
    print("\nFetching NQ price from Yahoo...")
    price = manager.get_price("NQ")
    if price:
        print(f"  Symbol: {price.symbol}")
        print(f"  Close: {price.close}")
        print(f"  Time: {price.timestamp}")
    else:
        print("  Failed to fetch price")
    
    # Fetch history
    print("\nFetching NQ history...")
    history = manager.get_history("NQ", days=10)
    print(f"  Got {len(history)} bars")
    if history:
        print(f"  First: {history[0].timestamp} - {history[0].close}")
        print(f"  Last: {history[-1].timestamp} - {history[-1].close}")
