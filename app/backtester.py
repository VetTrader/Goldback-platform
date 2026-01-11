"""
================================================================================
                    GOLDBACH BACKTESTING ENGINE
                    Historical Testing & Statistics
================================================================================

Пълен backtesting модул за Goldbach Trading System:
- Historical data loading (CSV, Yahoo Finance)
- Strategy backtesting
- Walk-forward analysis
- Monte Carlo simulation
- Comprehensive statistics
- Equity curve generation
- Trade journal

================================================================================
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import os

from app.goldbach_engine import (
    GoldbachEngine, TradeSetup, Bias, TradePlan, Layer,
    PO3Range, BiasAnalysis, DEFAULT_PO3
)


# ==============================================================================
#                              DATA CLASSES
# ==============================================================================

@dataclass
class BacktestTrade:
    """Единична сделка от backtest."""
    id: int
    entry_time: datetime
    exit_time: datetime
    symbol: str
    direction: str  # LONG / SHORT
    plan: TradePlan
    entry_price: float
    exit_price: float
    stop_loss: float
    target_1: float
    target_2: float
    position_size: float
    pnl: float
    pnl_pct: float
    result: str  # WIN / LOSS / BREAKEVEN
    exit_reason: str  # TARGET_1, TARGET_2, STOP_LOSS, TIME_EXIT
    bars_held: int
    mae: float  # Maximum Adverse Excursion
    mfe: float  # Maximum Favorable Excursion
    signal_strength: str
    goldbach_time: bool
    amd_cycle: str
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "symbol": self.symbol,
            "direction": self.direction,
            "plan": self.plan.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "position_size": self.position_size,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "result": self.result,
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
            "mae": self.mae,
            "mfe": self.mfe,
            "signal_strength": self.signal_strength,
            "goldbach_time": self.goldbach_time,
            "amd_cycle": self.amd_cycle
        }


@dataclass
class BacktestStatistics:
    """Пълна статистика от backtest."""
    # General
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    
    # Win Rate
    win_rate: float = 0.0
    
    # Profit/Loss
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Risk Metrics
    profit_factor: float = 0.0
    expectancy: float = 0.0
    risk_reward_ratio: float = 0.0
    
    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_drawdown: float = 0.0
    max_drawdown_duration: int = 0  # in bars
    
    # Streaks
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0
    
    # Time Analysis
    avg_bars_held: float = 0.0
    avg_bars_winner: float = 0.0
    avg_bars_loser: float = 0.0
    
    # By Plan
    stats_by_plan: Dict[str, Dict] = field(default_factory=dict)
    
    # By Signal Strength
    stats_by_strength: Dict[str, Dict] = field(default_factory=dict)
    
    # By Day of Week
    stats_by_day: Dict[str, Dict] = field(default_factory=dict)
    
    # By AMD Cycle
    stats_by_amd: Dict[str, Dict] = field(default_factory=dict)
    
    # Monthly Returns
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    
    # Equity Curve
    equity_curve: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "risk_reward_ratio": self.risk_reward_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_drawdown": self.avg_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "avg_bars_held": self.avg_bars_held,
            "avg_bars_winner": self.avg_bars_winner,
            "avg_bars_loser": self.avg_bars_loser,
            "stats_by_plan": self.stats_by_plan,
            "stats_by_strength": self.stats_by_strength,
            "stats_by_day": self.stats_by_day,
            "stats_by_amd": self.stats_by_amd,
            "monthly_returns": self.monthly_returns,
            "equity_curve": self.equity_curve
        }


@dataclass 
class BacktestConfig:
    """Конфигурация за backtest."""
    initial_capital: float = 10000.0
    position_size_pct: float = 1.0  # % of capital per trade
    max_positions: int = 1
    commission: float = 0.0  # per trade
    slippage: float = 0.0  # points
    
    # Risk Management
    use_stop_loss: bool = True
    use_trailing_stop: bool = False
    trailing_stop_pct: float = 0.5
    
    # Filters
    min_signal_strength: str = "MEDIUM"  # WEAK, MEDIUM, STRONG, EXCELLENT, PERFECT
    allowed_plans: List[TradePlan] = field(default_factory=lambda: list(TradePlan))
    allowed_amd_cycles: List[str] = field(default_factory=lambda: ["M", "D1"])
    require_goldbach_time: bool = False
    
    # Time Filters
    max_bars_in_trade: int = 50
    
    # PO3 Settings
    po3_size: int = DEFAULT_PO3


# ==============================================================================
#                              BACKTESTING ENGINE
# ==============================================================================

class BacktestEngine:
    """
    Goldbach Backtesting Engine.
    
    Поддържа:
    - Historical data от CSV или DataFrame
    - Пълен backtest на Goldbach стратегията
    - Walk-forward оптимизация
    - Monte Carlo симулация
    - Детайлна статистика
    """
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.engine = GoldbachEngine(self.config.po3_size)
        self.trades: List[BacktestTrade] = []
        self.statistics: Optional[BacktestStatistics] = None
        
        # Signal strength order
        self.strength_order = ["WEAK", "MEDIUM", "STRONG", "EXCELLENT", "PERFECT"]
    
    # ==========================================================================
    #                          DATA LOADING
    # ==========================================================================
    
    def load_csv(self, filepath: str, 
                 date_column: str = "Date",
                 ohlc_columns: Dict[str, str] = None) -> pd.DataFrame:
        """Зарежда данни от CSV файл."""
        
        df = pd.read_csv(filepath)
        
        # Map columns
        if ohlc_columns:
            df = df.rename(columns=ohlc_columns)
        
        # Parse dates
        df[date_column] = pd.to_datetime(df[date_column])
        df = df.set_index(date_column)
        df = df.sort_index()
        
        # Ensure required columns
        required = ['Open', 'High', 'Low', 'Close']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        return df
    
    def load_yahoo(self, symbol: str, 
                   start_date: str, 
                   end_date: str = None,
                   interval: str = "1d") -> pd.DataFrame:
        """Зарежда данни от Yahoo Finance."""
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval=interval)
            
            return df
            
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip install yfinance")
    
    # ==========================================================================
    #                          BACKTESTING
    # ==========================================================================
    
    def run_backtest(self, data: pd.DataFrame, 
                     symbol: str = "NQ") -> BacktestStatistics:
        """
        Изпълнява пълен backtest на данните.
        
        Args:
            data: DataFrame с OHLC данни
            symbol: Symbol name
            
        Returns:
            BacktestStatistics обект
        """
        self.trades = []
        capital = self.config.initial_capital
        equity_curve = [capital]
        
        in_trade = False
        current_trade = None
        trade_id = 0
        
        # Convert to list for faster iteration
        dates = data.index.tolist()
        opens = data['Open'].tolist()
        highs = data['High'].tolist()
        lows = data['Low'].tolist()
        closes = data['Close'].tolist()
        
        for i in range(1, len(data)):
            current_date = dates[i]
            current_open = opens[i]
            current_high = highs[i]
            current_low = lows[i]
            current_close = closes[i]
            
            prev_close = closes[i-1]
            
            # If in trade, check for exit
            if in_trade and current_trade:
                exit_info = self._check_exit(
                    current_trade, current_high, current_low, current_close, i
                )
                
                if exit_info:
                    # Close trade
                    trade = self._close_trade(
                        current_trade, 
                        current_date,
                        exit_info['price'],
                        exit_info['reason'],
                        i - current_trade['entry_bar'],
                        current_trade['mae'],
                        current_trade['mfe']
                    )
                    
                    self.trades.append(trade)
                    capital += trade.pnl
                    equity_curve.append(capital)
                    
                    in_trade = False
                    current_trade = None
                    continue
                else:
                    # Update MAE/MFE
                    if current_trade['direction'] == "LONG":
                        current_trade['mae'] = min(current_trade['mae'], 
                                                   current_low - current_trade['entry_price'])
                        current_trade['mfe'] = max(current_trade['mfe'],
                                                   current_high - current_trade['entry_price'])
                    else:
                        current_trade['mae'] = min(current_trade['mae'],
                                                   current_trade['entry_price'] - current_high)
                        current_trade['mfe'] = max(current_trade['mfe'],
                                                   current_trade['entry_price'] - current_low)
            
            # If not in trade, look for entry
            if not in_trade:
                # Generate setup
                setup = self.engine.generate_setup(
                    prev_close, symbol, 
                    self.config.po3_size,
                    time=current_date if isinstance(current_date, datetime) else datetime.now()
                )
                
                if setup and self._filter_setup(setup):
                    trade_id += 1
                    
                    # Calculate position size
                    position_size = (capital * self.config.position_size_pct / 100)
                    
                    current_trade = {
                        'id': trade_id,
                        'entry_bar': i,
                        'entry_time': current_date,
                        'symbol': symbol,
                        'direction': "LONG" if setup.bias == Bias.BULLISH else "SHORT",
                        'plan': setup.plan,
                        'entry_price': setup.entry_price,
                        'stop_loss': setup.stop_loss,
                        'target_1': setup.targets[0]['price'] if setup.targets else setup.entry_price,
                        'target_2': setup.targets[1]['price'] if len(setup.targets) > 1 else setup.entry_price,
                        'position_size': position_size,
                        'signal_strength': setup.signal_strength,
                        'goldbach_time': setup.goldbach_time_confirm,
                        'amd_cycle': setup.amd_cycle.value,
                        'mae': 0,
                        'mfe': 0
                    }
                    
                    in_trade = True
        
        # Close any remaining trade
        if in_trade and current_trade:
            trade = self._close_trade(
                current_trade,
                dates[-1],
                closes[-1],
                "TIME_EXIT",
                len(data) - current_trade['entry_bar'],
                current_trade['mae'],
                current_trade['mfe']
            )
            self.trades.append(trade)
            capital += trade.pnl
            equity_curve.append(capital)
        
        # Calculate statistics
        self.statistics = self._calculate_statistics(equity_curve)
        
        return self.statistics
    
    def _filter_setup(self, setup: TradeSetup) -> bool:
        """Проверява дали setup-ът отговаря на филтрите."""
        
        # Signal strength filter
        min_idx = self.strength_order.index(self.config.min_signal_strength)
        current_idx = self.strength_order.index(setup.signal_strength)
        if current_idx < min_idx:
            return False
        
        # Plan filter
        if setup.plan not in self.config.allowed_plans:
            return False
        
        # AMD cycle filter
        if setup.amd_cycle.value not in self.config.allowed_amd_cycles:
            return False
        
        # Goldbach time filter
        if self.config.require_goldbach_time and not setup.goldbach_time_confirm:
            return False
        
        return True
    
    def _check_exit(self, trade: Dict, high: float, low: float, 
                    close: float, current_bar: int) -> Optional[Dict]:
        """Проверява за изход от сделката."""
        
        bars_held = current_bar - trade['entry_bar']
        
        # Max bars exit
        if bars_held >= self.config.max_bars_in_trade:
            return {'price': close, 'reason': 'TIME_EXIT'}
        
        if trade['direction'] == "LONG":
            # Stop loss
            if self.config.use_stop_loss and low <= trade['stop_loss']:
                return {'price': trade['stop_loss'], 'reason': 'STOP_LOSS'}
            
            # Target 2 (full exit)
            if high >= trade['target_2']:
                return {'price': trade['target_2'], 'reason': 'TARGET_2'}
            
            # Target 1 (partial - simplified as full for now)
            if high >= trade['target_1']:
                return {'price': trade['target_1'], 'reason': 'TARGET_1'}
        
        else:  # SHORT
            # Stop loss
            if self.config.use_stop_loss and high >= trade['stop_loss']:
                return {'price': trade['stop_loss'], 'reason': 'STOP_LOSS'}
            
            # Target 2 (full exit)
            if low <= trade['target_2']:
                return {'price': trade['target_2'], 'reason': 'TARGET_2'}
            
            # Target 1
            if low <= trade['target_1']:
                return {'price': trade['target_1'], 'reason': 'TARGET_1'}
        
        return None
    
    def _close_trade(self, trade: Dict, exit_time: datetime, 
                     exit_price: float, exit_reason: str,
                     bars_held: int, mae: float, mfe: float) -> BacktestTrade:
        """Затваря сделка и изчислява резултата."""
        
        if trade['direction'] == "LONG":
            pnl = (exit_price - trade['entry_price']) * trade['position_size']
        else:
            pnl = (trade['entry_price'] - exit_price) * trade['position_size']
        
        pnl -= self.config.commission * 2  # Entry + exit
        pnl -= self.config.slippage * 2
        
        pnl_pct = (pnl / trade['position_size']) * 100
        
        if pnl > 0:
            result = "WIN"
        elif pnl < 0:
            result = "LOSS"
        else:
            result = "BREAKEVEN"
        
        return BacktestTrade(
            id=trade['id'],
            entry_time=trade['entry_time'],
            exit_time=exit_time,
            symbol=trade['symbol'],
            direction=trade['direction'],
            plan=trade['plan'],
            entry_price=trade['entry_price'],
            exit_price=exit_price,
            stop_loss=trade['stop_loss'],
            target_1=trade['target_1'],
            target_2=trade['target_2'],
            position_size=trade['position_size'],
            pnl=pnl,
            pnl_pct=pnl_pct,
            result=result,
            exit_reason=exit_reason,
            bars_held=bars_held,
            mae=mae,
            mfe=mfe,
            signal_strength=trade['signal_strength'],
            goldbach_time=trade['goldbach_time'],
            amd_cycle=trade['amd_cycle']
        )
    
    # ==========================================================================
    #                          STATISTICS
    # ==========================================================================
    
    def _calculate_statistics(self, equity_curve: List[float]) -> BacktestStatistics:
        """Изчислява пълна статистика от trades."""
        
        stats = BacktestStatistics()
        
        if not self.trades:
            return stats
        
        stats.total_trades = len(self.trades)
        stats.equity_curve = equity_curve
        
        # Win/Loss counts
        wins = [t for t in self.trades if t.result == "WIN"]
        losses = [t for t in self.trades if t.result == "LOSS"]
        breakevens = [t for t in self.trades if t.result == "BREAKEVEN"]
        
        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        stats.breakeven_trades = len(breakevens)
        
        # Win Rate
        if stats.total_trades > 0:
            stats.win_rate = (stats.winning_trades / stats.total_trades) * 100
        
        # P&L
        stats.total_pnl = sum(t.pnl for t in self.trades)
        stats.total_pnl_pct = sum(t.pnl_pct for t in self.trades)
        
        if wins:
            stats.avg_win = sum(t.pnl for t in wins) / len(wins)
            stats.largest_win = max(t.pnl for t in wins)
        
        if losses:
            stats.avg_loss = sum(t.pnl for t in losses) / len(losses)
            stats.largest_loss = min(t.pnl for t in losses)
        
        # Profit Factor
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1
        stats.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Expectancy
        if stats.total_trades > 0:
            stats.expectancy = stats.total_pnl / stats.total_trades
        
        # Risk/Reward
        if stats.avg_loss != 0:
            stats.risk_reward_ratio = abs(stats.avg_win / stats.avg_loss) if stats.avg_loss else 0
        
        # Drawdown
        peak = equity_curve[0]
        drawdowns = []
        dd_start = 0
        max_dd_duration = 0
        
        for i, equity in enumerate(equity_curve):
            if equity > peak:
                peak = equity
                if dd_start > 0:
                    max_dd_duration = max(max_dd_duration, i - dd_start)
                dd_start = i
            dd = peak - equity
            drawdowns.append(dd)
        
        stats.max_drawdown = max(drawdowns) if drawdowns else 0
        stats.max_drawdown_pct = (stats.max_drawdown / self.config.initial_capital) * 100
        stats.avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else 0
        stats.max_drawdown_duration = max_dd_duration
        
        # Consecutive wins/losses
        current_streak = 0
        max_wins = 0
        max_losses = 0
        last_result = None
        
        for trade in self.trades:
            if trade.result == last_result:
                current_streak += 1
            else:
                current_streak = 1
            
            if trade.result == "WIN":
                max_wins = max(max_wins, current_streak)
            elif trade.result == "LOSS":
                max_losses = max(max_losses, current_streak)
            
            last_result = trade.result
        
        stats.max_consecutive_wins = max_wins
        stats.max_consecutive_losses = max_losses
        
        # Time analysis
        if self.trades:
            stats.avg_bars_held = sum(t.bars_held for t in self.trades) / len(self.trades)
        if wins:
            stats.avg_bars_winner = sum(t.bars_held for t in wins) / len(wins)
        if losses:
            stats.avg_bars_loser = sum(t.bars_held for t in losses) / len(losses)
        
        # Stats by Plan
        stats.stats_by_plan = self._stats_by_category('plan')
        
        # Stats by Signal Strength
        stats.stats_by_strength = self._stats_by_category('signal_strength')
        
        # Stats by Day
        stats.stats_by_day = self._stats_by_day()
        
        # Stats by AMD Cycle
        stats.stats_by_amd = self._stats_by_category('amd_cycle')
        
        # Monthly returns
        stats.monthly_returns = self._calculate_monthly_returns()
        
        return stats
    
    def _stats_by_category(self, category: str) -> Dict[str, Dict]:
        """Групира статистика по категория."""
        result = {}
        
        for trade in self.trades:
            key = getattr(trade, category)
            if isinstance(key, TradePlan):
                key = key.value
            
            if key not in result:
                result[key] = {'trades': 0, 'wins': 0, 'pnl': 0}
            
            result[key]['trades'] += 1
            if trade.result == "WIN":
                result[key]['wins'] += 1
            result[key]['pnl'] += trade.pnl
        
        # Calculate win rates
        for key in result:
            if result[key]['trades'] > 0:
                result[key]['win_rate'] = (result[key]['wins'] / result[key]['trades']) * 100
            else:
                result[key]['win_rate'] = 0
        
        return result
    
    def _stats_by_day(self) -> Dict[str, Dict]:
        """Групира статистика по ден от седмицата."""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        result = {day: {'trades': 0, 'wins': 0, 'pnl': 0} for day in days}
        
        for trade in self.trades:
            if isinstance(trade.entry_time, datetime):
                day = days[trade.entry_time.weekday()]
                result[day]['trades'] += 1
                if trade.result == "WIN":
                    result[day]['wins'] += 1
                result[day]['pnl'] += trade.pnl
        
        for day in result:
            if result[day]['trades'] > 0:
                result[day]['win_rate'] = (result[day]['wins'] / result[day]['trades']) * 100
        
        return result
    
    def _calculate_monthly_returns(self) -> Dict[str, float]:
        """Изчислява месечни returns."""
        monthly = {}
        
        for trade in self.trades:
            if isinstance(trade.exit_time, datetime):
                key = trade.exit_time.strftime('%Y-%m')
                if key not in monthly:
                    monthly[key] = 0
                monthly[key] += trade.pnl
        
        return monthly
    
    # ==========================================================================
    #                          MONTE CARLO SIMULATION
    # ==========================================================================
    
    def monte_carlo(self, num_simulations: int = 1000) -> Dict:
        """
        Monte Carlo симулация за оценка на риска.
        
        Разбърква реда на сделките и изчислява:
        - Разпределение на крайния капитал
        - Разпределение на max drawdown
        - Confidence intervals
        """
        if not self.trades:
            return {}
        
        pnls = [t.pnl for t in self.trades]
        initial_capital = self.config.initial_capital
        
        final_capitals = []
        max_drawdowns = []
        
        for _ in range(num_simulations):
            # Shuffle P&Ls
            shuffled = np.random.permutation(pnls)
            
            # Calculate equity curve
            equity = initial_capital
            peak = initial_capital
            max_dd = 0
            
            for pnl in shuffled:
                equity += pnl
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100
                max_dd = max(max_dd, dd)
            
            final_capitals.append(equity)
            max_drawdowns.append(max_dd)
        
        return {
            'final_capital': {
                'mean': np.mean(final_capitals),
                'std': np.std(final_capitals),
                'min': np.min(final_capitals),
                'max': np.max(final_capitals),
                'percentile_5': np.percentile(final_capitals, 5),
                'percentile_25': np.percentile(final_capitals, 25),
                'percentile_50': np.percentile(final_capitals, 50),
                'percentile_75': np.percentile(final_capitals, 75),
                'percentile_95': np.percentile(final_capitals, 95),
            },
            'max_drawdown': {
                'mean': np.mean(max_drawdowns),
                'std': np.std(max_drawdowns),
                'min': np.min(max_drawdowns),
                'max': np.max(max_drawdowns),
                'percentile_95': np.percentile(max_drawdowns, 95),
            },
            'risk_of_ruin': sum(1 for fc in final_capitals if fc <= 0) / num_simulations * 100
        }
    
    # ==========================================================================
    #                          WALK-FORWARD ANALYSIS
    # ==========================================================================
    
    def walk_forward(self, data: pd.DataFrame,
                     in_sample_pct: float = 0.7,
                     num_folds: int = 5) -> List[Dict]:
        """
        Walk-forward анализ.
        
        Разделя данните на in-sample и out-of-sample периоди
        и тества робустността на стратегията.
        """
        results = []
        total_len = len(data)
        fold_size = total_len // num_folds
        
        for fold in range(num_folds):
            fold_start = fold * fold_size
            fold_end = fold_start + fold_size
            
            in_sample_end = fold_start + int(fold_size * in_sample_pct)
            
            # In-sample period
            in_sample_data = data.iloc[fold_start:in_sample_end]
            
            # Out-of-sample period
            out_sample_data = data.iloc[in_sample_end:fold_end]
            
            # Run backtests
            in_stats = self.run_backtest(in_sample_data)
            out_stats = self.run_backtest(out_sample_data)
            
            results.append({
                'fold': fold + 1,
                'in_sample': {
                    'start': in_sample_data.index[0].isoformat() if len(in_sample_data) > 0 else None,
                    'end': in_sample_data.index[-1].isoformat() if len(in_sample_data) > 0 else None,
                    'trades': in_stats.total_trades,
                    'win_rate': in_stats.win_rate,
                    'pnl': in_stats.total_pnl
                },
                'out_of_sample': {
                    'start': out_sample_data.index[0].isoformat() if len(out_sample_data) > 0 else None,
                    'end': out_sample_data.index[-1].isoformat() if len(out_sample_data) > 0 else None,
                    'trades': out_stats.total_trades,
                    'win_rate': out_stats.win_rate,
                    'pnl': out_stats.total_pnl
                },
                'robustness_score': self._calculate_robustness(in_stats, out_stats)
            })
        
        return results
    
    def _calculate_robustness(self, in_stats: BacktestStatistics, 
                               out_stats: BacktestStatistics) -> float:
        """Изчислява robustness score."""
        if in_stats.win_rate == 0:
            return 0
        
        # Compare win rates
        win_rate_ratio = out_stats.win_rate / in_stats.win_rate if in_stats.win_rate > 0 else 0
        
        # Compare profit factors
        pf_ratio = out_stats.profit_factor / in_stats.profit_factor if in_stats.profit_factor > 0 else 0
        
        # Score (0-100)
        score = (win_rate_ratio * 50 + pf_ratio * 50)
        return min(100, max(0, score))
    
    # ==========================================================================
    #                          REPORTING
    # ==========================================================================
    
    def generate_report(self) -> str:
        """Генерира текстов отчет от backtesting."""
        if not self.statistics:
            return "No backtest results available. Run backtest first."
        
        s = self.statistics
        
        report = f"""
{'='*70}
                    GOLDBACH BACKTEST REPORT
{'='*70}

SUMMARY
-------
Total Trades:       {s.total_trades}
Winning Trades:     {s.winning_trades}
Losing Trades:      {s.losing_trades}
Win Rate:           {s.win_rate:.1f}%

PROFIT & LOSS
-------------
Total P&L:          ${s.total_pnl:,.2f}
Average Win:        ${s.avg_win:,.2f}
Average Loss:       ${s.avg_loss:,.2f}
Largest Win:        ${s.largest_win:,.2f}
Largest Loss:       ${s.largest_loss:,.2f}
Profit Factor:      {s.profit_factor:.2f}
Expectancy:         ${s.expectancy:,.2f}

RISK METRICS
------------
Risk/Reward Ratio:  {s.risk_reward_ratio:.2f}
Max Drawdown:       ${s.max_drawdown:,.2f} ({s.max_drawdown_pct:.1f}%)
Avg Drawdown:       ${s.avg_drawdown:,.2f}
Max DD Duration:    {s.max_drawdown_duration} bars

STREAKS
-------
Max Consecutive Wins:   {s.max_consecutive_wins}
Max Consecutive Losses: {s.max_consecutive_losses}

TIME ANALYSIS
-------------
Avg Bars Held:      {s.avg_bars_held:.1f}
Avg Bars (Winner):  {s.avg_bars_winner:.1f}
Avg Bars (Loser):   {s.avg_bars_loser:.1f}

PERFORMANCE BY TRADE PLAN
-------------------------"""
        
        for plan, stats in s.stats_by_plan.items():
            report += f"\n{plan:20} | Trades: {stats['trades']:3} | Win Rate: {stats.get('win_rate', 0):5.1f}% | P&L: ${stats['pnl']:,.2f}"
        
        report += f"""

PERFORMANCE BY SIGNAL STRENGTH
------------------------------"""
        
        for strength, stats in s.stats_by_strength.items():
            report += f"\n{strength:10} | Trades: {stats['trades']:3} | Win Rate: {stats.get('win_rate', 0):5.1f}% | P&L: ${stats['pnl']:,.2f}"
        
        report += f"""

PERFORMANCE BY DAY
------------------"""
        
        for day, stats in s.stats_by_day.items():
            if stats['trades'] > 0:
                report += f"\n{day:10} | Trades: {stats['trades']:3} | Win Rate: {stats.get('win_rate', 0):5.1f}% | P&L: ${stats['pnl']:,.2f}"
        
        report += f"""

{'='*70}
"""
        
        return report
    
    def export_trades(self, filepath: str):
        """Експортира trades в JSON."""
        with open(filepath, 'w') as f:
            json.dump([t.to_dict() for t in self.trades], f, indent=2)
    
    def export_statistics(self, filepath: str):
        """Експортира статистика в JSON."""
        if self.statistics:
            with open(filepath, 'w') as f:
                json.dump(self.statistics.to_dict(), f, indent=2)


# ==============================================================================
#                              SINGLETON
# ==============================================================================

# Global backtest engine
backtest_engine = BacktestEngine()


# ==============================================================================
#                              TEST
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  GOLDBACH BACKTESTING ENGINE TEST")
    print("=" * 70)
    
    # Create sample data
    dates = pd.date_range(start='2025-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # Simulate price data
    base_price = 21000
    prices = [base_price]
    for _ in range(99):
        change = np.random.randn() * 50
        prices.append(prices[-1] + change)
    
    df = pd.DataFrame({
        'Open': prices,
        'High': [p + abs(np.random.randn() * 30) for p in prices],
        'Low': [p - abs(np.random.randn() * 30) for p in prices],
        'Close': [p + np.random.randn() * 20 for p in prices]
    }, index=dates)
    
    print(f"\nSample data: {len(df)} bars")
    print(f"Price range: {df['Low'].min():.0f} - {df['High'].max():.0f}")
    
    # Configure backtest
    config = BacktestConfig(
        initial_capital=10000,
        position_size_pct=2.0,
        min_signal_strength="MEDIUM",
        po3_size=729
    )
    
    # Run backtest
    engine = BacktestEngine(config)
    stats = engine.run_backtest(df, "NQ")
    
    # Print report
    print(engine.generate_report())
    
    # Monte Carlo
    print("\nMONTE CARLO SIMULATION (1000 runs)")
    print("-" * 40)
    mc = engine.monte_carlo(1000)
    if mc:
        print(f"Final Capital (mean): ${mc['final_capital']['mean']:,.2f}")
        print(f"Final Capital (5th percentile): ${mc['final_capital']['percentile_5']:,.2f}")
        print(f"Max Drawdown (95th percentile): {mc['max_drawdown']['percentile_95']:.1f}%")
        print(f"Risk of Ruin: {mc['risk_of_ruin']:.2f}%")
