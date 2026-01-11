"""
Goldbach Unified Trading Platform
=================================

A comprehensive trading platform combining:
- Goldbach Trifecta (3-Layer Framework)
- Goldbach Fundamentals (Timing Filters)

Modules:
    goldbach_engine - Core Goldbach calculations and signal generation
    backtester - Historical backtesting and statistics
    main - Flask web application and API
"""

from app.goldbach_engine import GoldbachEngine, engine
from app.backtester import BacktestEngine, BacktestConfig

__version__ = '1.0.0'
__author__ = 'Trading Platform'

__all__ = [
    'GoldbachEngine',
    'engine',
    'BacktestEngine', 
    'BacktestConfig'
]
