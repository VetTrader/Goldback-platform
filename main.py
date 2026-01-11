"""
================================================================================
                    GOLDBACH UNIFIED TRADING PLATFORM
                    Main Application - Cloud Ready
================================================================================

Flask application combining:
- Real-time market analysis
- Signal generation
- Backtesting interface
- Statistics dashboard
- Telegram/Discord notifications
- API endpoints
- TradingView webhooks
- Scheduled automatic analysis
- Multiple data providers

================================================================================
"""

from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from goldbach_engine import (
    GoldbachEngine, TradeSetup, Bias, TradePlan, Layer,
    AMDCycle, DEFAULT_PO3, GOLDBACH_LEVELS, MONTHLY_PARTITIONS
)
from backtester import BacktestEngine, BacktestConfig, BacktestStatistics
from data_feeds import (
    DataFeedManager, DataFeedConfig, PriceData,
    TradingViewWebhook, create_yahoo_feed, create_twelvedata_feed
)
from scheduler import GoldbachScheduler, ScheduledJob, PriceAlert, JobType


# ==============================================================================
#                              APP CONFIGURATION
# ==============================================================================

class Config:
    """Application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'goldbach-trading-secret-2026')
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    
    # Database
    DATABASE_PATH = os.environ.get('DATABASE_PATH', 'data/goldbach.db')
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    
    # Discord
    DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')
    
    # Trading
    DEFAULT_SYMBOL = os.environ.get('DEFAULT_SYMBOL', 'NQ')
    DEFAULT_PO3_SIZE = int(os.environ.get('DEFAULT_PO3_SIZE', DEFAULT_PO3))
    SYMBOLS = os.environ.get('SYMBOLS', 'NQ,ES,EURUSD,XAUUSD').split(',')
    
    # Data Providers
    TWELVEDATA_API_KEY = os.environ.get('TWELVEDATA_API_KEY', '')
    ALPHAVANTAGE_API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY', '')
    POLYGON_API_KEY = os.environ.get('POLYGON_API_KEY', '')
    
    # TradingView
    TRADINGVIEW_WEBHOOK_SECRET = os.environ.get('TRADINGVIEW_WEBHOOK_SECRET', '')
    
    # Scheduler
    ENABLE_SCHEDULER = os.environ.get('ENABLE_SCHEDULER', 'True').lower() == 'true'
    AUTO_ANALYSIS_INTERVAL = int(os.environ.get('AUTO_ANALYSIS_INTERVAL', 60))  # minutes


config = Config()


# ==============================================================================
#                              APP INITIALIZATION
# ==============================================================================

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')
app.config.from_object(config)

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize engines
goldbach_engine = GoldbachEngine(config.DEFAULT_PO3_SIZE)
backtest_engine = BacktestEngine()

# Initialize data feeds
data_manager = DataFeedManager()

# Initialize TradingView webhook handler
tradingview_webhook = TradingViewWebhook(config.TRADINGVIEW_WEBHOOK_SECRET)

# Initialize scheduler
scheduler = GoldbachScheduler(goldbach_engine, data_manager)

# Store for signals and statistics
signals_store: List[Dict] = []
statistics_store: Dict = {}

# Flag to track initialization
_initialized = False


# ==============================================================================
#                              STARTUP INITIALIZATION
# ==============================================================================

def initialize_data_feeds():
    """Initialize data feeds based on configuration."""
    # Always add Yahoo Finance (free, no API key)
    yahoo_config = create_yahoo_feed(config.SYMBOLS, interval="1d", refresh_seconds=60)
    data_manager.add_provider("yahoo", yahoo_config)
    
    # Add Twelve Data if API key provided
    if config.TWELVEDATA_API_KEY:
        td_config = create_twelvedata_feed(
            config.TWELVEDATA_API_KEY, 
            config.SYMBOLS,
            interval="1day"
        )
        data_manager.add_provider("twelvedata", td_config)
        data_manager.set_primary("twelvedata")
        logger.info("Twelve Data provider configured")
    
    # Register price update callback
    def on_price_update(price: PriceData):
        # Emit to websocket
        socketio.emit('price_update', price.to_dict())
        # Check alerts
        scheduler.check_alerts(price.symbol, price.close)
    
    data_manager.on_price_update(on_price_update)
    logger.info(f"Data feeds initialized with {len(data_manager.providers)} providers")


def initialize_scheduler():
    """Initialize scheduler with default jobs."""
    if not config.ENABLE_SCHEDULER:
        logger.info("Scheduler disabled")
        return
    
    # Setup default jobs
    scheduler.setup_default_jobs(config.SYMBOLS)
    
    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started")


def initialize_tradingview_webhook():
    """Setup TradingView webhook handler."""
    def on_tv_alert(alert: Dict):
        symbol = alert.get("symbol", "UNKNOWN")
        price = alert.get("price", 0)
        
        logger.info(f"TradingView alert: {symbol} @ {price}")
        
        # Run Goldbach analysis
        if price > 0:
            setup = goldbach_engine.generate_setup(price, symbol)
            if setup:
                signal_dict = setup.to_dict()
                signals_store.append(signal_dict)
                socketio.emit('new_signal', signal_dict)
                
                # Send notification
                scheduler.notification_manager.send(
                    scheduler._format_setup_message(setup)
                )
    
    tradingview_webhook.on_alert(on_tv_alert)


# ==============================================================================
#                              HELPER FUNCTIONS
# ==============================================================================

def send_telegram(message: str):
    """Send message to Telegram."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=data)
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def format_signal_message(setup: TradeSetup) -> str:
    """Format signal for notification."""
    emoji = "🟢" if setup.bias == Bias.BULLISH else "🔴"
    
    message = f"""
{emoji} <b>GOLDBACH SIGNAL</b> {emoji}

<b>Symbol:</b> {setup.symbol}
<b>Plan:</b> {setup.plan.value}
<b>Bias:</b> {setup.bias.value} ({setup.confidence}%)
<b>Strength:</b> {setup.signal_strength}

<b>Entry Zone:</b> {setup.entry_zone[0]:.2f} - {setup.entry_zone[1]:.2f}
<b>Stop Loss:</b> {setup.stop_loss:.2f}

<b>Targets:</b>
"""
    for t in setup.targets:
        message += f"  • {t['name']}: {t['price']:.2f}\n"
    
    if setup.goldbach_time_confirm:
        message += "\n✅ Goldbach Time Confirmation"
    
    message += f"\n<b>AMD Cycle:</b> {setup.amd_cycle.value}"
    
    return message


# ==============================================================================
#                              WEB ROUTES
# ==============================================================================

@app.route('/')
def index():
    """Main dashboard."""
    return render_template('dashboard.html')


@app.route('/backtest')
def backtest_page():
    """Backtesting page."""
    return render_template('backtest.html')


@app.route('/signals')
def signals_page():
    """Signals history page."""
    return render_template('signals.html')


@app.route('/docs')
def docs_page():
    """Documentation page."""
    return render_template('docs.html')


# ==============================================================================
#                              API ROUTES - ANALYSIS
# ==============================================================================

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """
    Analyze a price and generate full Goldbach analysis.
    
    Request:
        {
            "price": 21500,
            "symbol": "NQ",
            "po3_size": 729,
            "trend_days": 0
        }
    """
    data = request.get_json() or {}
    
    price = data.get('price')
    if not price:
        return jsonify({'error': 'Price is required'}), 400
    
    try:
        price = float(price)
        symbol = data.get('symbol', config.DEFAULT_SYMBOL)
        po3_size = int(data.get('po3_size', config.DEFAULT_PO3_SIZE))
        trend_days = int(data.get('trend_days', 0))
        
        # Get position info
        pos_info = goldbach_engine.get_position_info(price, po3_size)
        
        # Get bias analysis
        bias = goldbach_engine.analyze_bias(price, po3_size, trend_days)
        
        # Get Goldbach time
        gb_time = goldbach_engine.analyze_goldbach_time()
        
        # Get AMD cycle
        amd = goldbach_engine.get_amd_cycle()
        
        # Get monthly partition
        partition = goldbach_engine.get_monthly_partition_info()
        
        # Generate setup if applicable
        setup = goldbach_engine.generate_setup(price, symbol, po3_size, trend_days)
        
        return jsonify({
            'price': price,
            'symbol': symbol,
            'position': pos_info,
            'bias': bias.to_dict(),
            'goldbach_time': gb_time.to_dict(),
            'amd_cycle': amd.to_dict(),
            'monthly_partition': partition,
            'setup': setup.to_dict() if setup else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/levels/<int:range_num>')
def api_levels(range_num: int):
    """Get all Goldbach levels for a range."""
    try:
        po3_size = request.args.get('po3_size', config.DEFAULT_PO3_SIZE, type=int)
        
        # Calculate range boundaries
        range_low = range_num * po3_size
        range_high = range_low + po3_size
        
        levels = []
        for level_pct, info in GOLDBACH_LEVELS.items():
            price = range_low + (level_pct / 100) * po3_size
            levels.append({
                'level': level_pct,
                'price': price,
                'name': info['name'],
                'ict_name': info['ict'],
                'layer': info['layer'].value if info['layer'] else None
            })
        
        return jsonify({
            'range_num': range_num,
            'range_low': range_low,
            'range_high': range_high,
            'po3_size': po3_size,
            'levels': levels
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/goldbach-time')
def api_goldbach_time():
    """Get current Goldbach time analysis."""
    gb_time = goldbach_engine.analyze_goldbach_time()
    next_times = goldbach_engine.get_next_goldbach_times(count=5)
    
    return jsonify({
        'current': gb_time.to_dict(),
        'next_goldbach_times': [t.to_dict() for t in next_times]
    })


@app.route('/api/amd-cycle')
def api_amd_cycle():
    """Get current AMD cycle."""
    amd = goldbach_engine.get_amd_cycle()
    return jsonify(amd.to_dict())


@app.route('/api/partition')
def api_partition():
    """Get current monthly partition info."""
    partition = goldbach_engine.get_monthly_partition_info()
    return jsonify(partition)


# ==============================================================================
#                              API ROUTES - SIGNALS
# ==============================================================================

@app.route('/api/signal', methods=['POST'])
def api_generate_signal():
    """
    Generate a trading signal.
    
    Request:
        {
            "price": 21500,
            "symbol": "NQ",
            "send_notification": true
        }
    """
    data = request.get_json() or {}
    
    price = data.get('price')
    if not price:
        return jsonify({'error': 'Price is required'}), 400
    
    try:
        price = float(price)
        symbol = data.get('symbol', config.DEFAULT_SYMBOL)
        send_notification = data.get('send_notification', False)
        
        # Generate setup
        setup = goldbach_engine.generate_setup(price, symbol)
        
        if not setup:
            return jsonify({
                'signal': None,
                'message': 'No clear setup at current price'
            })
        
        signal_dict = setup.to_dict()
        
        # Store signal
        signals_store.append(signal_dict)
        if len(signals_store) > 100:
            signals_store.pop(0)
        
        # Send notification if requested
        if send_notification:
            message = format_signal_message(setup)
            send_telegram(message)
        
        # Emit to websocket
        socketio.emit('new_signal', signal_dict)
        
        return jsonify({
            'signal': signal_dict,
            'notification_sent': send_notification
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/signals')
def api_get_signals():
    """Get stored signals."""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(signals_store[-limit:])


# ==============================================================================
#                              API ROUTES - BACKTESTING
# ==============================================================================

@app.route('/api/backtest', methods=['POST'])
def api_run_backtest():
    """
    Run a backtest.
    
    Request:
        {
            "data": [...],  // OHLC data array
            "config": {
                "initial_capital": 10000,
                "position_size_pct": 2.0,
                "min_signal_strength": "MEDIUM",
                "po3_size": 729
            }
        }
    """
    data = request.get_json() or {}
    
    ohlc_data = data.get('data')
    bt_config = data.get('config', {})
    
    if not ohlc_data:
        return jsonify({'error': 'OHLC data is required'}), 400
    
    try:
        import pandas as pd
        
        # Convert to DataFrame
        df = pd.DataFrame(ohlc_data)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        
        # Ensure proper column names
        col_map = {
            'open': 'Open', 'high': 'High', 
            'low': 'Low', 'close': 'Close'
        }
        df = df.rename(columns=col_map)
        
        # Create config
        config = BacktestConfig(
            initial_capital=bt_config.get('initial_capital', 10000),
            position_size_pct=bt_config.get('position_size_pct', 2.0),
            min_signal_strength=bt_config.get('min_signal_strength', 'MEDIUM'),
            po3_size=bt_config.get('po3_size', DEFAULT_PO3)
        )
        
        # Run backtest
        engine = BacktestEngine(config)
        stats = engine.run_backtest(df)
        
        # Get Monte Carlo if requested
        monte_carlo = None
        if bt_config.get('run_monte_carlo'):
            monte_carlo = engine.monte_carlo(1000)
        
        return jsonify({
            'statistics': stats.to_dict(),
            'trades': [t.to_dict() for t in engine.trades],
            'monte_carlo': monte_carlo,
            'report': engine.generate_report()
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/backtest/walk-forward', methods=['POST'])
def api_walk_forward():
    """Run walk-forward analysis."""
    data = request.get_json() or {}
    
    ohlc_data = data.get('data')
    num_folds = data.get('num_folds', 5)
    
    if not ohlc_data:
        return jsonify({'error': 'OHLC data is required'}), 400
    
    try:
        import pandas as pd
        
        df = pd.DataFrame(ohlc_data)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        
        col_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}
        df = df.rename(columns=col_map)
        
        engine = BacktestEngine()
        results = engine.walk_forward(df, num_folds=num_folds)
        
        return jsonify({
            'results': results,
            'avg_robustness': sum(r['robustness_score'] for r in results) / len(results)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==============================================================================
#                              API ROUTES - TRADINGVIEW WEBHOOK
# ==============================================================================

@app.route('/api/webhook/tradingview', methods=['POST'])
def api_tradingview_webhook():
    """
    TradingView webhook endpoint.
    
    Setup in TradingView:
    1. Create Alert
    2. Set Webhook URL: https://your-domain.com/api/webhook/tradingview
    3. Set Message:
       {
           "symbol": "{{ticker}}",
           "price": {{close}},
           "action": "{{strategy.order.action}}",
           "time": "{{time}}"
       }
    """
    try:
        data = request.get_json() or {}
        headers = dict(request.headers)
        
        success = tradingview_webhook.process_webhook(data, headers)
        
        if success:
            return jsonify({'status': 'ok', 'processed': True})
        else:
            return jsonify({'status': 'error', 'processed': False}), 400
            
    except Exception as e:
        logger.error(f"TradingView webhook error: {e}")
        return jsonify({'error': str(e)}), 500


# ==============================================================================
#                              API ROUTES - DATA FEEDS
# ==============================================================================

@app.route('/api/data/price/<symbol>')
def api_get_price(symbol: str):
    """Get current price for symbol."""
    try:
        price = data_manager.get_price(symbol)
        if price:
            return jsonify(price.to_dict())
        else:
            return jsonify({'error': 'Could not fetch price'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/history/<symbol>')
def api_get_history(symbol: str):
    """Get historical data for symbol."""
    try:
        days = request.args.get('days', 100, type=int)
        history = data_manager.get_history(symbol, days)
        
        return jsonify({
            'symbol': symbol,
            'bars': len(history),
            'data': [p.to_dict() for p in history]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/providers')
def api_get_providers():
    """Get data provider status."""
    return jsonify(data_manager.get_status())


# ==============================================================================
#                              API ROUTES - SCHEDULER
# ==============================================================================

@app.route('/api/scheduler/status')
def api_scheduler_status():
    """Get scheduler status."""
    return jsonify(scheduler.get_status())


@app.route('/api/scheduler/jobs', methods=['GET', 'POST'])
def api_scheduler_jobs():
    """Manage scheduler jobs."""
    if request.method == 'GET':
        return jsonify({
            'jobs': {jid: job.to_dict() for jid, job in scheduler.jobs.items()}
        })
    
    elif request.method == 'POST':
        data = request.get_json() or {}
        
        job = ScheduledJob(
            id=data.get('id', f"custom_{len(scheduler.jobs)}"),
            name=data.get('name', 'Custom Job'),
            job_type=JobType[data.get('job_type', 'ANALYSIS').upper()],
            schedule=data.get('schedule', 'every_1h'),
            config=data.get('config', {})
        )
        
        scheduler.add_job(job)
        return jsonify({'status': 'ok', 'job': job.to_dict()})


@app.route('/api/scheduler/jobs/<job_id>', methods=['DELETE'])
def api_delete_job(job_id: str):
    """Delete a scheduler job."""
    if scheduler.remove_job(job_id):
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'Job not found'}), 404


@app.route('/api/scheduler/run/<job_id>', methods=['POST'])
def api_run_job(job_id: str):
    """Manually run a job."""
    if job_id in scheduler.jobs:
        scheduler._execute_job(scheduler.jobs[job_id])
        return jsonify({'status': 'ok', 'executed': True})
    return jsonify({'error': 'Job not found'}), 404


# ==============================================================================
#                              API ROUTES - ALERTS
# ==============================================================================

@app.route('/api/alerts', methods=['GET', 'POST'])
def api_alerts():
    """Manage price alerts."""
    if request.method == 'GET':
        return jsonify({
            'alerts': {
                aid: {
                    'symbol': a.symbol,
                    'condition': a.condition,
                    'price': a.price,
                    'enabled': a.enabled,
                    'triggered': a.triggered
                }
                for aid, a in scheduler.alerts.items()
            }
        })
    
    elif request.method == 'POST':
        data = request.get_json() or {}
        
        alert = PriceAlert(
            id=data.get('id', f"alert_{len(scheduler.alerts)}"),
            symbol=data.get('symbol', 'NQ'),
            condition=data.get('condition', 'above'),
            price=float(data.get('price', 0))
        )
        
        scheduler.add_alert(alert)
        return jsonify({'status': 'ok', 'alert_id': alert.id})


@app.route('/api/alerts/<alert_id>', methods=['DELETE'])
def api_delete_alert(alert_id: str):
    """Delete a price alert."""
    if scheduler.remove_alert(alert_id):
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'Alert not found'}), 404


# ==============================================================================
#                              API ROUTES - STATISTICS
# ==============================================================================

@app.route('/api/statistics')
def api_statistics():
    """Get global statistics."""
    total_signals = len(signals_store)
    
    if signals_store:
        bullish = sum(1 for s in signals_store if s.get('bias') == 'BULLISH')
        bearish = total_signals - bullish
        
        by_plan = {}
        by_strength = {}
        
        for s in signals_store:
            plan = s.get('plan', 'UNKNOWN')
            strength = s.get('signal_strength', 'UNKNOWN')
            
            by_plan[plan] = by_plan.get(plan, 0) + 1
            by_strength[strength] = by_strength.get(strength, 0) + 1
    else:
        bullish = bearish = 0
        by_plan = {}
        by_strength = {}
    
    return jsonify({
        'total_signals': total_signals,
        'bullish_signals': bullish,
        'bearish_signals': bearish,
        'by_plan': by_plan,
        'by_strength': by_strength,
        'last_updated': datetime.now().isoformat()
    })


# ==============================================================================
#                              API ROUTES - REFERENCE DATA
# ==============================================================================

@app.route('/api/reference/levels')
def api_reference_levels():
    """Get all Goldbach levels reference."""
    return jsonify({
        'levels': {
            k: {
                'name': v['name'],
                'ict': v['ict'],
                'layer': v['layer'].value if v['layer'] else None
            }
            for k, v in GOLDBACH_LEVELS.items()
        }
    })


@app.route('/api/reference/partitions')
def api_reference_partitions():
    """Get monthly partitions reference."""
    return jsonify({'partitions': MONTHLY_PARTITIONS})


@app.route('/api/reference/plans')
def api_reference_plans():
    """Get trade plans reference."""
    plans = {
        'EINSTEIN': {
            'description': 'Най-печелившият план - влизане в GAP между [11-17] или [83-89]',
            'entry_zone': 'Liquidity Layer GAP',
            'targets': '[47-53] partial, [41-59] full',
            'best_for': 'Reversal от extremes'
        },
        'LIQUIDITY': {
            'description': 'Влизане при stop run близо до range edges',
            'entry_zone': '[3-11] или [89-97]',
            'targets': 'External liquidity',
            'best_for': 'Stop runs'
        },
        'FLOW_CONTINUATION': {
            'description': 'Следване на momentum в Flow Layer',
            'entry_zone': '[29-35] или [65-71]',
            'targets': 'Rebalance → противоположен Flow',
            'best_for': 'Trend continuation'
        },
        'REBALANCE': {
            'description': 'Trading the range в Rebalance Layer',
            'entry_zone': '[41-47] или [53-59]',
            'targets': 'Противоположен edge на Rebalance',
            'best_for': 'Range trading'
        },
        'STOP_RUN': {
            'description': 'Класически ICT stop run setup',
            'entry_zone': 'Range extreme с breaker',
            'targets': 'Liquidity Void [29/71]',
            'best_for': 'Manipulation phases'
        }
    }
    return jsonify({'plans': plans})


# ==============================================================================
#                              WEBSOCKET EVENTS
# ==============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('connected', {'status': 'ok', 'timestamp': datetime.now().isoformat()})


@socketio.on('request_analysis')
def handle_analysis_request(data):
    """Handle analysis request via websocket."""
    price = data.get('price')
    if price:
        pos_info = goldbach_engine.get_position_info(float(price))
        bias = goldbach_engine.analyze_bias(float(price))
        emit('analysis_result', {
            'position': pos_info,
            'bias': bias.to_dict()
        })


@socketio.on('subscribe_signals')
def handle_subscribe_signals():
    """Subscribe to real-time signals."""
    emit('subscribed', {'channel': 'signals'})


# ==============================================================================
#                              HEALTH CHECK
# ==============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })


# ==============================================================================
#                              ERROR HANDLERS
# ==============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# ==============================================================================
#                              MAIN
# ==============================================================================

def create_app():
    """Application factory."""
    # Initialize on first request
    with app.app_context():
        initialize_data_feeds()
        initialize_tradingview_webhook()
        initialize_scheduler()
    
    return app


# ==============================================================================
#                              MODULE-LEVEL INITIALIZATION
#                              (Runs when gunicorn imports the module)
# ==============================================================================

def _do_initialization():
    """Run initialization once at module load."""
    global _initialized
    if _initialized:
        return
    
    logger.info("=" * 50)
    logger.info("  GOLDBACH PLATFORM - Initializing...")
    logger.info("=" * 50)
    
    try:
        initialize_data_feeds()
        logger.info("✓ Data feeds initialized")
    except Exception as e:
        logger.error(f"✗ Data feeds error: {e}")
    
    try:
        initialize_tradingview_webhook()
        logger.info("✓ TradingView webhook initialized")
    except Exception as e:
        logger.error(f"✗ TradingView webhook error: {e}")
    
    try:
        initialize_scheduler()
        logger.info("✓ Scheduler initialized")
    except Exception as e:
        logger.error(f"✗ Scheduler error: {e}")
    
    _initialized = True
    logger.info("=" * 50)
    logger.info("  GOLDBACH PLATFORM - Ready!")
    logger.info("=" * 50)


# Run initialization when module is loaded
_do_initialization()


if __name__ == '__main__':
    print("=" * 70)
    print("    GOLDBACH UNIFIED TRADING PLATFORM")
    print("    Version 1.0.0 - Cloud Ready")
    print("=" * 70)
    print(f"\n    Starting server at http://{config.HOST}:{config.PORT}")
    print("=" * 70)
    
    # Initialization already done at module level
    # Start data feed auto-refresh
    data_manager.start_all()
    
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG
    )
