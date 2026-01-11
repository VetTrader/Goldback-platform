"""
================================================================================
                    GOLDBACH SCHEDULER MODULE
                    Automatic Analysis & Notifications
================================================================================

Автоматично изпълнява:
- Scheduled анализи (всеки час, при отваряне на сесия, etc.)
- Price monitoring с alerts
- Daily/Weekly reports
- Signal generation при определени условия

================================================================================
"""

import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================================
#                              ENUMS & CLASSES
# ==============================================================================

class JobType(Enum):
    ANALYSIS = "analysis"
    SIGNAL_CHECK = "signal_check"
    DAILY_REPORT = "daily_report"
    PRICE_ALERT = "price_alert"
    CUSTOM = "custom"


class NotificationType(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"
    WEBHOOK = "webhook"


@dataclass
class ScheduledJob:
    """Scheduled job configuration."""
    id: str
    name: str
    job_type: JobType
    schedule: str  # cron-like or interval
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    config: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "job_type": self.job_type.value,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "config": self.config
        }


@dataclass
class PriceAlert:
    """Price alert configuration."""
    id: str
    symbol: str
    condition: str  # "above", "below", "cross"
    price: float
    enabled: bool = True
    triggered: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    
    def check(self, current_price: float) -> bool:
        """Check if alert condition is met."""
        if not self.enabled or self.triggered:
            return False
        
        if self.condition == "above" and current_price > self.price:
            return True
        elif self.condition == "below" and current_price < self.price:
            return True
        elif self.condition == "cross":
            # Would need previous price to check cross
            return False
        
        return False


# ==============================================================================
#                              NOTIFICATION MANAGER
# ==============================================================================

class NotificationManager:
    """
    Управлява изпращането на нотификации през различни канали.
    """
    
    def __init__(self):
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.custom_webhooks: List[str] = []
    
    def send(self, message: str, notification_type: NotificationType = None,
             html: bool = True) -> bool:
        """Send notification to all configured channels or specific one."""
        success = False
        
        if notification_type:
            types = [notification_type]
        else:
            types = [NotificationType.TELEGRAM, NotificationType.DISCORD]
        
        for nt in types:
            if nt == NotificationType.TELEGRAM:
                if self._send_telegram(message, html):
                    success = True
            elif nt == NotificationType.DISCORD:
                if self._send_discord(message):
                    success = True
            elif nt == NotificationType.WEBHOOK:
                if self._send_webhooks(message):
                    success = True
        
        return success
    
    def _send_telegram(self, message: str, html: bool = True) -> bool:
        """Send Telegram message."""
        if not self.telegram_token or not self.telegram_chat_id:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML" if html else None
            }
            
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    def _send_discord(self, message: str) -> bool:
        """Send Discord message via webhook."""
        if not self.discord_webhook:
            return False
        
        try:
            # Convert HTML to markdown-ish
            clean_message = message.replace("<b>", "**").replace("</b>", "**")
            clean_message = clean_message.replace("<i>", "_").replace("</i>", "_")
            
            data = {"content": clean_message}
            response = requests.post(self.discord_webhook, json=data, timeout=10)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Discord send error: {e}")
            return False
    
    def _send_webhooks(self, message: str) -> bool:
        """Send to custom webhooks."""
        success = False
        for webhook in self.custom_webhooks:
            try:
                response = requests.post(webhook, json={"message": message}, timeout=10)
                if response.status_code == 200:
                    success = True
            except Exception as e:
                logger.error(f"Webhook send error: {e}")
        return success
    
    def add_webhook(self, url: str):
        """Add custom webhook."""
        self.custom_webhooks.append(url)


# ==============================================================================
#                              SCHEDULER
# ==============================================================================

class GoldbachScheduler:
    """
    Job scheduler за автоматични анализи и нотификации.
    
    Поддържа:
    - Interval-based jobs (every X minutes/hours)
    - Time-based jobs (at specific times)
    - Session-based jobs (market open/close)
    - Price alerts
    """
    
    # Trading sessions (CET times)
    SESSIONS = {
        "asian_open": "00:00",
        "asian_close": "09:00",
        "london_open": "08:00",
        "london_close": "17:00",
        "ny_open": "14:30",
        "ny_close": "21:00",
    }
    
    # Default analysis times
    DEFAULT_ANALYSIS_TIMES = [
        "08:00",  # London open
        "09:00",  # Post-London
        "14:30",  # NY open
        "15:30",  # Post-NY open
        "21:00",  # NY close
    ]
    
    def __init__(self, goldbach_engine=None, data_manager=None):
        self.goldbach_engine = goldbach_engine
        self.data_manager = data_manager
        self.notification_manager = NotificationManager()
        
        self.jobs: Dict[str, ScheduledJob] = {}
        self.alerts: Dict[str, PriceAlert] = {}
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        self._job_handlers: Dict[JobType, Callable] = {
            JobType.ANALYSIS: self._run_analysis,
            JobType.SIGNAL_CHECK: self._run_signal_check,
            JobType.DAILY_REPORT: self._run_daily_report,
            JobType.PRICE_ALERT: self._run_price_alerts,
        }
    
    # ==========================================================================
    #                          JOB MANAGEMENT
    # ==========================================================================
    
    def add_job(self, job: ScheduledJob) -> bool:
        """Add a scheduled job."""
        self.jobs[job.id] = job
        self._calculate_next_run(job)
        logger.info(f"Added job: {job.name} ({job.schedule})")
        return True
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if job_id in self.jobs:
            del self.jobs[job_id]
            return True
        return False
    
    def enable_job(self, job_id: str) -> bool:
        """Enable a job."""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = True
            return True
        return False
    
    def disable_job(self, job_id: str) -> bool:
        """Disable a job."""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = False
            return True
        return False
    
    def _calculate_next_run(self, job: ScheduledJob):
        """Calculate next run time for job."""
        now = datetime.now()
        schedule = job.schedule
        
        # Interval format: "every_Xm" or "every_Xh"
        if schedule.startswith("every_"):
            interval_str = schedule[6:]
            if interval_str.endswith("m"):
                minutes = int(interval_str[:-1])
                job.next_run = now + timedelta(minutes=minutes)
            elif interval_str.endswith("h"):
                hours = int(interval_str[:-1])
                job.next_run = now + timedelta(hours=hours)
        
        # Time format: "HH:MM"
        elif ":" in schedule:
            target_time = datetime.strptime(schedule, "%H:%M").time()
            job.next_run = datetime.combine(now.date(), target_time)
            if job.next_run <= now:
                job.next_run += timedelta(days=1)
        
        # Daily at specific times
        elif schedule == "daily":
            # Next day at midnight
            job.next_run = datetime.combine(now.date() + timedelta(days=1), 
                                           datetime.min.time())
    
    # ==========================================================================
    #                          ALERT MANAGEMENT
    # ==========================================================================
    
    def add_alert(self, alert: PriceAlert) -> bool:
        """Add a price alert."""
        self.alerts[alert.id] = alert
        logger.info(f"Added alert: {alert.symbol} {alert.condition} {alert.price}")
        return True
    
    def remove_alert(self, alert_id: str) -> bool:
        """Remove a price alert."""
        if alert_id in self.alerts:
            del self.alerts[alert_id]
            return True
        return False
    
    def check_alerts(self, symbol: str, price: float):
        """Check all alerts for a symbol."""
        for alert_id, alert in list(self.alerts.items()):
            if alert.symbol != symbol:
                continue
            
            if alert.check(price):
                alert.triggered = True
                self._trigger_alert(alert, price)
    
    def _trigger_alert(self, alert: PriceAlert, current_price: float):
        """Handle triggered alert."""
        message = f"""
🚨 <b>PRICE ALERT TRIGGERED</b> 🚨

<b>Symbol:</b> {alert.symbol}
<b>Condition:</b> {alert.condition} {alert.price}
<b>Current:</b> {current_price}
<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}
"""
        self.notification_manager.send(message)
        logger.info(f"Alert triggered: {alert.symbol} {alert.condition} {alert.price}")
    
    # ==========================================================================
    #                          SCHEDULER LOOP
    # ==========================================================================
    
    def start(self):
        """Start the scheduler."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")
    
    def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            now = datetime.now()
            
            # Check jobs
            for job_id, job in list(self.jobs.items()):
                if not job.enabled:
                    continue
                
                if job.next_run and now >= job.next_run:
                    self._execute_job(job)
                    job.last_run = now
                    self._calculate_next_run(job)
            
            # Sleep for a bit
            time.sleep(10)  # Check every 10 seconds
    
    def _execute_job(self, job: ScheduledJob):
        """Execute a scheduled job."""
        logger.info(f"Executing job: {job.name}")
        
        handler = self._job_handlers.get(job.job_type)
        if handler:
            try:
                handler(job)
            except Exception as e:
                logger.error(f"Job execution error ({job.name}): {e}")
        else:
            logger.warning(f"No handler for job type: {job.job_type}")
    
    # ==========================================================================
    #                          JOB HANDLERS
    # ==========================================================================
    
    def _run_analysis(self, job: ScheduledJob):
        """Run market analysis job."""
        symbols = job.config.get("symbols", ["NQ"])
        
        for symbol in symbols:
            # Get current price
            price = None
            if self.data_manager:
                price_data = self.data_manager.get_price(symbol)
                if price_data:
                    price = price_data.close
            
            if not price:
                logger.warning(f"Could not get price for {symbol}")
                continue
            
            # Run Goldbach analysis
            if self.goldbach_engine:
                setup = self.goldbach_engine.generate_setup(price, symbol)
                
                if setup:
                    message = self._format_setup_message(setup)
                    self.notification_manager.send(message)
                else:
                    # Send position update anyway
                    pos_info = self.goldbach_engine.get_position_info(price)
                    bias = self.goldbach_engine.analyze_bias(price)
                    
                    message = f"""
📊 <b>GOLDBACH ANALYSIS</b> - {symbol}

<b>Price:</b> {price}
<b>Position:</b> {pos_info['position_str']}
<b>Layer:</b> {pos_info['layer']}
<b>Bias:</b> {bias.bias.value} ({bias.confidence}%)

<i>No clear setup at current price</i>
"""
                    self.notification_manager.send(message)
    
    def _run_signal_check(self, job: ScheduledJob):
        """Check for signal conditions."""
        symbols = job.config.get("symbols", ["NQ"])
        min_strength = job.config.get("min_strength", "STRONG")
        
        for symbol in symbols:
            price = None
            if self.data_manager:
                price_data = self.data_manager.get_price(symbol)
                if price_data:
                    price = price_data.close
            
            if not price or not self.goldbach_engine:
                continue
            
            setup = self.goldbach_engine.generate_setup(price, symbol)
            
            if setup:
                # Check signal strength
                strength_order = ["WEAK", "MEDIUM", "STRONG", "EXCELLENT", "PERFECT"]
                if strength_order.index(setup.signal_strength) >= strength_order.index(min_strength):
                    message = self._format_setup_message(setup)
                    self.notification_manager.send(message)
    
    def _run_daily_report(self, job: ScheduledJob):
        """Generate daily summary report."""
        symbols = job.config.get("symbols", ["NQ", "ES", "EURUSD"])
        
        report_lines = ["📈 <b>DAILY GOLDBACH REPORT</b>\n"]
        report_lines.append(f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>\n")
        
        for symbol in symbols:
            price = None
            if self.data_manager:
                price_data = self.data_manager.get_price(symbol)
                if price_data:
                    price = price_data.close
            
            if not price or not self.goldbach_engine:
                continue
            
            pos_info = self.goldbach_engine.get_position_info(price)
            bias = self.goldbach_engine.analyze_bias(price)
            
            bias_emoji = "🟢" if bias.bias.value == "BULLISH" else "🔴" if bias.bias.value == "BEARISH" else "⚪"
            
            report_lines.append(f"\n<b>{symbol}</b> {bias_emoji}")
            report_lines.append(f"  Price: {price}")
            report_lines.append(f"  Position: {pos_info['position_str']} ({pos_info['layer']})")
            report_lines.append(f"  Bias: {bias.bias.value} ({bias.confidence}%)")
        
        # Add timing info
        if self.goldbach_engine:
            gb_time = self.goldbach_engine.analyze_goldbach_time()
            amd = self.goldbach_engine.get_amd_cycle()
            partition = self.goldbach_engine.get_monthly_partition_info()
            
            report_lines.append("\n<b>TIMING</b>")
            report_lines.append(f"  Goldbach Time: {'✅' if gb_time.is_goldbach else '❌'}")
            report_lines.append(f"  AMD Cycle: {amd.cycle_name}")
            report_lines.append(f"  Partition Day: {partition.get('partition_day', 'N/A')}")
        
        message = "\n".join(report_lines)
        self.notification_manager.send(message)
    
    def _run_price_alerts(self, job: ScheduledJob):
        """Check price alerts."""
        symbols = set(alert.symbol for alert in self.alerts.values() if alert.enabled)
        
        for symbol in symbols:
            if self.data_manager:
                price_data = self.data_manager.get_price(symbol)
                if price_data:
                    self.check_alerts(symbol, price_data.close)
    
    def _format_setup_message(self, setup) -> str:
        """Format setup as notification message."""
        emoji = "🟢" if setup.bias.value == "BULLISH" else "🔴"
        
        message = f"""
{emoji} <b>GOLDBACH SIGNAL</b> {emoji}

<b>Symbol:</b> {setup.symbol}
<b>Plan:</b> {setup.plan.value}
<b>Bias:</b> {setup.bias.value} ({setup.confidence}%)
<b>Strength:</b> {setup.signal_strength}

<b>Entry Zone:</b> {setup.entry_zone[0]:.2f} - {setup.entry_zone[1]:.2f}
<b>Entry:</b> {setup.entry_price:.2f}
<b>Stop Loss:</b> {setup.stop_loss:.2f}

<b>Targets:</b>
"""
        for t in setup.targets:
            message += f"  • {t['name']}: {t['price']:.2f}\n"
        
        if setup.goldbach_time_confirm:
            message += "\n✅ Goldbach Time Confirmation"
        
        message += f"\n<b>AMD:</b> {setup.amd_cycle.value}"
        message += f"\n<i>{datetime.now().strftime('%H:%M:%S')}</i>"
        
        return message
    
    # ==========================================================================
    #                          PRESET CONFIGURATIONS
    # ==========================================================================
    
    def setup_default_jobs(self, symbols: List[str] = None):
        """Setup default scheduled jobs."""
        if symbols is None:
            symbols = ["NQ"]
        
        # Analysis at key times
        for i, time_str in enumerate(self.DEFAULT_ANALYSIS_TIMES):
            job = ScheduledJob(
                id=f"analysis_{i}",
                name=f"Analysis at {time_str}",
                job_type=JobType.ANALYSIS,
                schedule=time_str,
                config={"symbols": symbols}
            )
            self.add_job(job)
        
        # Hourly signal check
        job = ScheduledJob(
            id="signal_check_hourly",
            name="Hourly Signal Check",
            job_type=JobType.SIGNAL_CHECK,
            schedule="every_1h",
            config={"symbols": symbols, "min_strength": "STRONG"}
        )
        self.add_job(job)
        
        # Daily report
        job = ScheduledJob(
            id="daily_report",
            name="Daily Report",
            job_type=JobType.DAILY_REPORT,
            schedule="21:00",
            config={"symbols": symbols}
        )
        self.add_job(job)
        
        # Price alert check every 5 minutes
        job = ScheduledJob(
            id="price_alerts",
            name="Price Alert Check",
            job_type=JobType.PRICE_ALERT,
            schedule="every_5m"
        )
        self.add_job(job)
        
        logger.info(f"Setup {len(self.jobs)} default jobs")
    
    def get_status(self) -> Dict:
        """Get scheduler status."""
        return {
            "running": self._running,
            "jobs": {jid: job.to_dict() for jid, job in self.jobs.items()},
            "alerts": {
                aid: {
                    "symbol": a.symbol,
                    "condition": a.condition,
                    "price": a.price,
                    "enabled": a.enabled,
                    "triggered": a.triggered
                }
                for aid, a in self.alerts.items()
            }
        }


# ==============================================================================
#                              GLOBAL INSTANCE
# ==============================================================================

scheduler = GoldbachScheduler()


# ==============================================================================
#                              TEST
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  SCHEDULER TEST")
    print("=" * 70)
    
    # Create scheduler
    sched = GoldbachScheduler()
    
    # Add test job
    job = ScheduledJob(
        id="test_job",
        name="Test Analysis",
        job_type=JobType.ANALYSIS,
        schedule="every_1m",
        config={"symbols": ["NQ"]}
    )
    sched.add_job(job)
    
    # Add test alert
    alert = PriceAlert(
        id="test_alert",
        symbol="NQ",
        condition="above",
        price=22000
    )
    sched.add_alert(alert)
    
    print("\nScheduler status:")
    print(json.dumps(sched.get_status(), indent=2, default=str))
