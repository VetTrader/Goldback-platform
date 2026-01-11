"""
================================================================================
                    GOLDBACH UNIFIED TRADING ENGINE
                    Trifecta + Fundamentals Combined
================================================================================

Пълна имплементация на Goldbach Trading System включваща:
- PO3 Dealing Ranges (9, 27, 81, 243, 729, 2187, 6561)
- Всички Goldbach нива (0-100)
- 3-Layer Framework (Liquidity, Flow, Rebalance)
- GIP Bias Detection
- Goldbach Time
- AMD Cycles
- Monthly Partitions
- 6 Trade Plans

Базирано на: Goldbach Trifecta + Goldbach Fundamentals by Hopiplaka
================================================================================
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json


# ==============================================================================
#                              ENUMS & CONSTANTS
# ==============================================================================

class Bias(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Layer(Enum):
    LIQUIDITY = "LIQUIDITY"
    FLOW = "FLOW"
    REBALANCE = "REBALANCE"


class TradePlan(Enum):
    EINSTEIN = "EINSTEIN"
    LIQUIDITY = "LIQUIDITY"
    FLOW_CONTINUATION = "FLOW_CONTINUATION"
    FLOW_REJECTION = "FLOW_REJECTION"
    REBALANCE = "REBALANCE"
    STOP_RUN = "STOP_RUN"


class AMDCycle(Enum):
    ASIAN = "A"        # 20:00-03:00 CET
    MANIPULATION = "M"  # 03:00-09:00 CET (London)
    DISTRIBUTION_1 = "D1"  # 09:00-12:00 CET (NY AM)
    DISTRIBUTION_2 = "D2"  # 12:00-16:00 CET (NY PM)


# PO3 Numbers (Powers of 3)
PO3_SIZES = [3, 9, 27, 81, 243, 729, 2187, 6561]
DEFAULT_PO3 = 729  # Recommended for daily trading

# Goldbach Levels (as percentages of range)
GOLDBACH_LEVELS = {
    0: {"name": "LOW", "ict": "Range Low", "layer": Layer.LIQUIDITY},
    3: {"name": "REJ", "ict": "Rejection Block", "layer": Layer.LIQUIDITY},
    7: {"name": "LLOD", "ict": "Last Line of Defence", "layer": Layer.LIQUIDITY},
    11: {"name": "IRL", "ict": "Order Block", "layer": Layer.LIQUIDITY},
    17: {"name": "GIP", "ict": "Fair Value Gap", "layer": Layer.LIQUIDITY},
    23: {"name": "nGB", "ict": "(non-Goldbach)", "layer": None},
    29: {"name": "FLOW", "ict": "Liquidity Void", "layer": Layer.FLOW},
    35: {"name": "nGB", "ict": "(non-Goldbach)", "layer": None},
    41: {"name": "EXT.REB", "ict": "Breaker", "layer": Layer.REBALANCE},
    47: {"name": "INT.REB", "ict": "Mitigation Block", "layer": Layer.REBALANCE},
    50: {"name": "EQ", "ict": "Equilibrium", "layer": Layer.REBALANCE},
    53: {"name": "INT.REB", "ict": "Mitigation Block", "layer": Layer.REBALANCE},
    59: {"name": "EXT.REB", "ict": "Breaker", "layer": Layer.REBALANCE},
    65: {"name": "nGB", "ict": "(non-Goldbach)", "layer": None},
    71: {"name": "FLOW", "ict": "Liquidity Void", "layer": Layer.FLOW},
    77: {"name": "nGB", "ict": "(non-Goldbach)", "layer": None},
    83: {"name": "GIP", "ict": "Fair Value Gap", "layer": Layer.LIQUIDITY},
    89: {"name": "IRL", "ict": "Order Block", "layer": Layer.LIQUIDITY},
    93: {"name": "LLOD", "ict": "Last Line of Defence", "layer": Layer.LIQUIDITY},
    97: {"name": "REJ", "ict": "Rejection Block", "layer": Layer.LIQUIDITY},
    100: {"name": "HIGH", "ict": "Range High", "layer": Layer.LIQUIDITY},
}

# Goldbach Numbers for time calculation
GOLDBACH_NUMBERS = [3, 11, 17, 29, 41, 47, 53, 59, 71, 83, 89, 97]

# Monthly Partition Start Days
MONTHLY_PARTITIONS = {
    1: {"start_day": 8, "number": 18},   # January
    2: {"start_day": 7, "number": 27},   # February
    3: {"start_day": 6, "number": 36},   # March
    4: {"start_day": 5, "number": 45},   # April
    5: {"start_day": 4, "number": 54},   # May
    6: {"start_day": 3, "number": 63},   # June
    7: {"start_day": 2, "number": 72},   # July
    8: {"start_day": 1, "number": 81},   # August
    9: {"start_day": 9, "number": 99},   # September
    10: {"start_day": 8, "number": 108}, # October
    11: {"start_day": 7, "number": 117}, # November
    12: {"start_day": 6, "number": 126}, # December
}


# ==============================================================================
#                              DATA CLASSES
# ==============================================================================

@dataclass
class GoldbachLevel:
    """Единично Goldbach ниво."""
    level_pct: int          # 0-100
    price: float
    name: str
    ict_name: str
    layer: Optional[Layer]
    is_goldbach: bool = True
    
    def to_dict(self) -> Dict:
        return {
            "level_pct": self.level_pct,
            "price": self.price,
            "name": self.name,
            "ict_name": self.ict_name,
            "layer": self.layer.value if self.layer else None,
            "is_goldbach": self.is_goldbach
        }


@dataclass
class PO3Range:
    """PO3 Dealing Range."""
    range_num: int
    low: float
    high: float
    size: int
    levels: List[GoldbachLevel] = field(default_factory=list)
    
    def get_level_price(self, level_pct: int) -> float:
        """Изчислява цената за дадено ниво."""
        return self.low + (level_pct / 100) * self.size
    
    def get_position(self, price: float) -> float:
        """Връща позицията (0-100) на цена в range-а."""
        if price < self.low:
            return 0
        if price > self.high:
            return 100
        return ((price - self.low) / self.size) * 100
    
    def to_dict(self) -> Dict:
        return {
            "range_num": self.range_num,
            "low": self.low,
            "high": self.high,
            "size": self.size,
            "levels": [l.to_dict() for l in self.levels]
        }


@dataclass
class BiasAnalysis:
    """Резултат от bias анализ."""
    bias: Bias
    confidence: int  # 0-100
    gip_level: int   # 17 or 83
    position: float  # Current position in range (0-100)
    layer: Layer
    reasoning: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "bias": self.bias.value,
            "confidence": self.confidence,
            "gip_level": self.gip_level,
            "position": self.position,
            "layer": self.layer.value,
            "reasoning": self.reasoning
        }


@dataclass
class GoldbachTime:
    """Goldbach Time анализ."""
    time: datetime
    hour: int
    minute: int
    sum_value: int
    is_goldbach: bool
    nearest_goldbach: int
    
    def to_dict(self) -> Dict:
        return {
            "time": self.time.isoformat(),
            "hour": self.hour,
            "minute": self.minute,
            "sum_value": self.sum_value,
            "is_goldbach": self.is_goldbach,
            "nearest_goldbach": self.nearest_goldbach
        }


@dataclass
class AMDInfo:
    """AMD Cycle информация."""
    cycle: AMDCycle
    cycle_name: str
    description: str
    trading_bias: str
    
    def to_dict(self) -> Dict:
        return {
            "cycle": self.cycle.value,
            "cycle_name": self.cycle_name,
            "description": self.description,
            "trading_bias": self.trading_bias
        }


@dataclass
class TradeSetup:
    """Пълен trade setup."""
    id: int
    timestamp: datetime
    symbol: str
    plan: TradePlan
    bias: Bias
    confidence: int
    entry_zone: Tuple[float, float]
    entry_price: float
    stop_loss: float
    targets: List[Dict[str, float]]
    invalidation: Dict[str, Any]
    reasoning: List[str]
    goldbach_time_confirm: bool
    amd_cycle: AMDCycle
    monthly_partition_day: int
    signal_strength: str  # WEAK, MEDIUM, STRONG, EXCELLENT, PERFECT
    status: str = "PENDING"
    result: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "plan": self.plan.value,
            "bias": self.bias.value,
            "confidence": self.confidence,
            "entry_zone": self.entry_zone,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "targets": self.targets,
            "invalidation": self.invalidation,
            "reasoning": self.reasoning,
            "goldbach_time_confirm": self.goldbach_time_confirm,
            "amd_cycle": self.amd_cycle.value,
            "monthly_partition_day": self.monthly_partition_day,
            "signal_strength": self.signal_strength,
            "status": self.status,
            "result": self.result
        }


# ==============================================================================
#                              GOLDBACH ENGINE
# ==============================================================================

class GoldbachEngine:
    """
    Главен двигател за Goldbach Trading System.
    
    Комбинира:
    - PO3 Range изчисления
    - 3-Layer Framework
    - GIP Bias Detection
    - Goldbach Time
    - AMD Cycles
    - Trade Plan генериране
    """
    
    def __init__(self, default_po3: int = DEFAULT_PO3):
        self.default_po3 = default_po3
        self.setup_counter = 0
        self._ranges_cache: Dict[Tuple[int, int], PO3Range] = {}
    
    # ==========================================================================
    #                          PO3 RANGE CALCULATIONS
    # ==========================================================================
    
    def calculate_range(self, price: float, po3_size: int = None) -> PO3Range:
        """
        Изчислява PO3 range за дадена цена.
        
        Formula: Range Low = floor(price / PO3) × PO3
        """
        po3 = po3_size or self.default_po3
        
        # За forex (с десетична точка) - премахваме точката
        price_int = int(price * 10000) if price < 100 else int(price)
        
        range_num = price_int // po3
        range_low = range_num * po3
        range_high = range_low + po3
        
        # Конвертираме обратно за forex
        if price < 100:
            range_low = range_low / 10000
            range_high = range_high / 10000
        
        # Създаваме range с нива
        po3_range = PO3Range(
            range_num=range_num,
            low=range_low,
            high=range_high,
            size=po3
        )
        
        # Добавяме Goldbach нива
        po3_range.levels = self._calculate_levels(po3_range)
        
        return po3_range
    
    def _calculate_levels(self, po3_range: PO3Range) -> List[GoldbachLevel]:
        """Изчислява всички Goldbach нива за range."""
        levels = []
        
        for level_pct, info in GOLDBACH_LEVELS.items():
            price = po3_range.get_level_price(level_pct)
            
            level = GoldbachLevel(
                level_pct=level_pct,
                price=price,
                name=f"{info['name']} [{level_pct}]" if level_pct not in [0, 50, 100] else info['name'],
                ict_name=info['ict'],
                layer=info['layer'],
                is_goldbach=level_pct not in [23, 35, 65, 77]
            )
            levels.append(level)
        
        return levels
    
    def get_position_info(self, price: float, po3_size: int = None) -> Dict:
        """Връща пълна информация за позицията на цената."""
        po3_range = self.calculate_range(price, po3_size)
        position = po3_range.get_position(price)
        
        # Намираме текущия layer
        layer = self._get_layer_for_position(position)
        
        # Намираме най-близкото ниво
        nearest_level = self._get_nearest_level(po3_range, price)
        
        return {
            "price": price,
            "range": po3_range.to_dict(),
            "position": position,
            "position_str": f"[{position:.0f}]",
            "layer": layer.value if layer else None,
            "nearest_level": nearest_level.to_dict() if nearest_level else None
        }
    
    def _get_layer_for_position(self, position: float) -> Optional[Layer]:
        """Определя layer-а за дадена позиция."""
        if position <= 17 or position >= 83:
            return Layer.LIQUIDITY
        elif 29 <= position <= 35 or 65 <= position <= 71:
            return Layer.FLOW
        elif 41 <= position <= 59:
            return Layer.REBALANCE
        else:
            return None
    
    def _get_nearest_level(self, po3_range: PO3Range, price: float) -> Optional[GoldbachLevel]:
        """Намира най-близкото Goldbach ниво."""
        if not po3_range.levels:
            return None
        
        return min(po3_range.levels, key=lambda l: abs(l.price - price))
    
    # ==========================================================================
    #                          BIAS DETECTION (GIP)
    # ==========================================================================
    
    def analyze_bias(self, price: float, po3_size: int = None, 
                     trend_days: int = 0) -> BiasAnalysis:
        """
        Анализира bias използвайки GIP (Goldbach Inversion Point).
        
        GIP [17] = под това ниво → BULLISH bias
        GIP [83] = над това ниво → BEARISH bias
        """
        po3_range = self.calculate_range(price, po3_size)
        position = po3_range.get_position(price)
        layer = self._get_layer_for_position(position)
        
        reasoning = []
        confidence = 50
        
        # Определяме bias според GIP
        if position <= 17:
            bias = Bias.BULLISH
            gip_level = 17
            confidence += 15
            reasoning.append(f"Цена под GIP [17] ({position:.0f}%) - силен BULLISH bias")
        elif position >= 83:
            bias = Bias.BEARISH
            gip_level = 83
            confidence += 15
            reasoning.append(f"Цена над GIP [83] ({position:.0f}%) - силен BEARISH bias")
        elif position < 50:
            bias = Bias.BULLISH
            gip_level = 17
            reasoning.append(f"Цена под EQ [50] ({position:.0f}%) - лек BULLISH bias")
        elif position > 50:
            bias = Bias.BEARISH
            gip_level = 83
            reasoning.append(f"Цена над EQ [50] ({position:.0f}%) - лек BEARISH bias")
        else:
            bias = Bias.NEUTRAL
            gip_level = 50
            reasoning.append("Цена на EQ [50] - NEUTRAL")
        
        # Layer бонус
        if layer == Layer.LIQUIDITY:
            confidence += 10
            reasoning.append(f"В Liquidity Layer - висока вероятност за reversal")
        elif layer == Layer.FLOW:
            confidence += 5
            reasoning.append(f"В Flow Layer - следвай momentum")
        elif layer == Layer.REBALANCE:
            reasoning.append(f"В Rebalance Layer - възможна консолидация")
        
        # Trend alignment
        if trend_days != 0:
            trend_aligned = (trend_days > 0 and bias == Bias.BULLISH) or \
                           (trend_days < 0 and bias == Bias.BEARISH)
            if trend_aligned:
                confidence += min(abs(trend_days) * 2, 10)
                reasoning.append(f"Trend alignment: {abs(trend_days)} дни в посоката")
            else:
                confidence -= min(abs(trend_days) * 2, 10)
                reasoning.append(f"Counter-trend: {abs(trend_days)} дни против bias")
        
        confidence = max(40, min(85, confidence))
        
        return BiasAnalysis(
            bias=bias,
            confidence=confidence,
            gip_level=gip_level,
            position=position,
            layer=layer or Layer.FLOW,
            reasoning=reasoning
        )
    
    # ==========================================================================
    #                          GOLDBACH TIME
    # ==========================================================================
    
    def analyze_goldbach_time(self, time: datetime = None) -> GoldbachTime:
        """
        Анализира дали времето е Goldbach Time.
        
        Formula: Hour + Minute = Goldbach Number?
        """
        if time is None:
            time = datetime.now()
        
        hour = time.hour
        minute = time.minute
        sum_value = hour + minute
        
        is_goldbach = sum_value in GOLDBACH_NUMBERS
        
        # Намираме най-близкото Goldbach число
        nearest = min(GOLDBACH_NUMBERS, key=lambda x: abs(x - sum_value))
        
        return GoldbachTime(
            time=time,
            hour=hour,
            minute=minute,
            sum_value=sum_value,
            is_goldbach=is_goldbach,
            nearest_goldbach=nearest
        )
    
    def get_next_goldbach_times(self, from_time: datetime = None, 
                                 count: int = 5) -> List[GoldbachTime]:
        """Връща следващите Goldbach времена."""
        if from_time is None:
            from_time = datetime.now()
        
        results = []
        current = from_time
        
        while len(results) < count:
            current = current + timedelta(minutes=1)
            gb_time = self.analyze_goldbach_time(current)
            if gb_time.is_goldbach:
                results.append(gb_time)
        
        return results
    
    # ==========================================================================
    #                          AMD CYCLES
    # ==========================================================================
    
    def get_amd_cycle(self, time: datetime = None, timezone: str = "CET") -> AMDInfo:
        """
        Определя текущия AMD цикъл.
        
        A = Asian (20:00-03:00 CET)
        M = Manipulation/London (03:00-09:00 CET)
        D1 = Distribution 1/NY AM (09:00-12:00 CET)
        D2 = Distribution 2/NY PM (12:00-16:00 CET)
        """
        if time is None:
            time = datetime.now()
        
        hour = time.hour
        
        if 20 <= hour <= 23 or 0 <= hour < 3:
            cycle = AMDCycle.ASIAN
            name = "Asian Session"
            description = "Consolidation phase - mark the range"
            trading_bias = "Изчакай - маркирай Asian range"
        elif 3 <= hour < 9:
            cycle = AMDCycle.MANIPULATION
            name = "London/Manipulation"
            description = "Creates HOD/LOD in 80%+ of cases"
            trading_bias = "Търси stop run на Asian range"
        elif 9 <= hour < 12:
            cycle = AMDCycle.DISTRIBUTION_1
            name = "NY AM (D1)"
            description = "Continuation or reversal of M move"
            trading_bias = "Continuation ако M е малък, Reversal ако M е голям"
        else:
            cycle = AMDCycle.DISTRIBUTION_2
            name = "NY PM (D2)"
            description = "Profit taking and reversals common"
            trading_bias = "Внимавай - чести reversals"
        
        return AMDInfo(
            cycle=cycle,
            cycle_name=name,
            description=description,
            trading_bias=trading_bias
        )
    
    # ==========================================================================
    #                          MONTHLY PARTITIONS
    # ==========================================================================
    
    def get_monthly_partition_info(self, date: datetime = None) -> Dict:
        """Връща информация за monthly partition."""
        if date is None:
            date = datetime.now()
        
        month = date.month
        day = date.day
        
        partition = MONTHLY_PARTITIONS.get(month, {})
        start_day = partition.get("start_day", 1)
        partition_number = partition.get("number", 0)
        
        # Изчисляваме кой ден от партицията сме
        if day >= start_day:
            partition_day = day - start_day + 1
        else:
            # Предходен месец
            partition_day = 0
        
        # Ключови дни
        key_days = {
            3: "POI clue day - търси gap/block/liquidity",
            11: "First major swing (Goldbach number)",
            17: "Second swing if day 11 didn't complete"
        }
        
        key_day_info = key_days.get(partition_day)
        
        return {
            "month": month,
            "day": day,
            "partition_start": start_day,
            "partition_number": partition_number,
            "partition_day": partition_day,
            "is_key_day": partition_day in key_days,
            "key_day_info": key_day_info,
            "expected_stop_run_pips": partition_number
        }
    
    # ==========================================================================
    #                          TRADE SETUP GENERATION
    # ==========================================================================
    
    def generate_setup(self, price: float, symbol: str = "NQ",
                       po3_size: int = None, trend_days: int = 0,
                       time: datetime = None) -> Optional[TradeSetup]:
        """
        Генерира пълен trade setup комбинирайки всички фактори.
        """
        if time is None:
            time = datetime.now()
        
        self.setup_counter += 1
        
        # Анализи
        po3_range = self.calculate_range(price, po3_size)
        position = po3_range.get_position(price)
        bias_analysis = self.analyze_bias(price, po3_size, trend_days)
        gb_time = self.analyze_goldbach_time(time)
        amd_info = self.get_amd_cycle(time)
        partition_info = self.get_monthly_partition_info(time)
        
        # Определяме trade plan
        plan, entry_zone, targets, invalidation = self._determine_trade_plan(
            po3_range, position, bias_analysis
        )
        
        if plan is None:
            return None
        
        # Entry price (средата на entry zone)
        entry_price = (entry_zone[0] + entry_zone[1]) / 2
        
        # Stop loss
        if bias_analysis.bias == Bias.BULLISH:
            stop_loss = invalidation.get("price", entry_zone[0] - 20)
        else:
            stop_loss = invalidation.get("price", entry_zone[1] + 20)
        
        # Signal strength
        signal_strength = self._calculate_signal_strength(
            bias_analysis, gb_time, amd_info, partition_info
        )
        
        # Reasoning
        reasoning = bias_analysis.reasoning.copy()
        reasoning.append(f"Trade Plan: {plan.value}")
        if gb_time.is_goldbach:
            reasoning.append(f"✓ Goldbach Time потвърждение ({gb_time.hour}:{gb_time.minute:02d})")
        reasoning.append(f"AMD Cycle: {amd_info.cycle_name}")
        if partition_info.get("is_key_day"):
            reasoning.append(f"✓ Key partition day: {partition_info['key_day_info']}")
        
        return TradeSetup(
            id=self.setup_counter,
            timestamp=time,
            symbol=symbol,
            plan=plan,
            bias=bias_analysis.bias,
            confidence=bias_analysis.confidence,
            entry_zone=entry_zone,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            invalidation=invalidation,
            reasoning=reasoning,
            goldbach_time_confirm=gb_time.is_goldbach,
            amd_cycle=amd_info.cycle,
            monthly_partition_day=partition_info.get("partition_day", 0),
            signal_strength=signal_strength
        )
    
    def _determine_trade_plan(self, po3_range: PO3Range, position: float,
                               bias: BiasAnalysis) -> Tuple[Optional[TradePlan], 
                                                            Tuple[float, float],
                                                            List[Dict], Dict]:
        """Определя подходящия trade plan."""
        
        # EINSTEIN PLAN - в Liquidity Layer с GAP
        if position <= 17 and bias.bias == Bias.BULLISH:
            return (
                TradePlan.EINSTEIN,
                (po3_range.get_level_price(11), po3_range.get_level_price(17)),
                [
                    {"name": "T1 (Partial)", "level": 47, "price": po3_range.get_level_price(47)},
                    {"name": "T2 (Full)", "level": 59, "price": po3_range.get_level_price(59)},
                ],
                {"level": 7, "price": po3_range.get_level_price(7), 
                 "description": "Под LLOD [7]"}
            )
        
        if position >= 83 and bias.bias == Bias.BEARISH:
            return (
                TradePlan.EINSTEIN,
                (po3_range.get_level_price(83), po3_range.get_level_price(89)),
                [
                    {"name": "T1 (Partial)", "level": 53, "price": po3_range.get_level_price(53)},
                    {"name": "T2 (Full)", "level": 41, "price": po3_range.get_level_price(41)},
                ],
                {"level": 93, "price": po3_range.get_level_price(93),
                 "description": "Над LLOD [93]"}
            )
        
        # LIQUIDITY PLAN - близо до edges
        if position <= 11 and bias.bias == Bias.BULLISH:
            return (
                TradePlan.LIQUIDITY,
                (po3_range.get_level_price(3), po3_range.get_level_price(11)),
                [
                    {"name": "T1", "level": 29, "price": po3_range.get_level_price(29)},
                    {"name": "T2", "level": 50, "price": po3_range.get_level_price(50)},
                ],
                {"level": 0, "price": po3_range.low, "description": "Под Range Low"}
            )
        
        if position >= 89 and bias.bias == Bias.BEARISH:
            return (
                TradePlan.LIQUIDITY,
                (po3_range.get_level_price(89), po3_range.get_level_price(97)),
                [
                    {"name": "T1", "level": 71, "price": po3_range.get_level_price(71)},
                    {"name": "T2", "level": 50, "price": po3_range.get_level_price(50)},
                ],
                {"level": 100, "price": po3_range.high, "description": "Над Range High"}
            )
        
        # FLOW CONTINUATION - в Flow Layer
        if 29 <= position <= 35 and bias.bias == Bias.BULLISH:
            return (
                TradePlan.FLOW_CONTINUATION,
                (po3_range.get_level_price(29), po3_range.get_level_price(35)),
                [
                    {"name": "T1", "level": 50, "price": po3_range.get_level_price(50)},
                    {"name": "T2", "level": 71, "price": po3_range.get_level_price(71)},
                ],
                {"level": 17, "price": po3_range.get_level_price(17),
                 "description": "Под GIP [17]"}
            )
        
        if 65 <= position <= 71 and bias.bias == Bias.BEARISH:
            return (
                TradePlan.FLOW_CONTINUATION,
                (po3_range.get_level_price(65), po3_range.get_level_price(71)),
                [
                    {"name": "T1", "level": 50, "price": po3_range.get_level_price(50)},
                    {"name": "T2", "level": 29, "price": po3_range.get_level_price(29)},
                ],
                {"level": 83, "price": po3_range.get_level_price(83),
                 "description": "Над GIP [83]"}
            )
        
        # REBALANCE PLAN - в Rebalance Layer
        if 41 <= position <= 59:
            if position <= 50:
                return (
                    TradePlan.REBALANCE,
                    (po3_range.get_level_price(41), po3_range.get_level_price(47)),
                    [
                        {"name": "T1", "level": 53, "price": po3_range.get_level_price(53)},
                        {"name": "T2", "level": 59, "price": po3_range.get_level_price(59)},
                    ],
                    {"level": 35, "price": po3_range.get_level_price(35),
                     "description": "Под Flow [35]"}
                )
            else:
                return (
                    TradePlan.REBALANCE,
                    (po3_range.get_level_price(53), po3_range.get_level_price(59)),
                    [
                        {"name": "T1", "level": 47, "price": po3_range.get_level_price(47)},
                        {"name": "T2", "level": 41, "price": po3_range.get_level_price(41)},
                    ],
                    {"level": 65, "price": po3_range.get_level_price(65),
                     "description": "Над Flow [65]"}
                )
        
        # Default - no clear setup
        return (None, (0, 0), [], {})
    
    def _calculate_signal_strength(self, bias: BiasAnalysis, 
                                    gb_time: GoldbachTime,
                                    amd: AMDInfo,
                                    partition: Dict) -> str:
        """Изчислява силата на сигнала."""
        score = 0
        
        # Bias confidence
        if bias.confidence >= 70:
            score += 2
        elif bias.confidence >= 60:
            score += 1
        
        # Goldbach Time
        if gb_time.is_goldbach:
            score += 2
        
        # AMD Cycle
        if amd.cycle in [AMDCycle.MANIPULATION, AMDCycle.DISTRIBUTION_1]:
            score += 1
        
        # Partition key day
        if partition.get("is_key_day"):
            score += 1
        
        # Layer bonus
        if bias.layer == Layer.LIQUIDITY:
            score += 1
        
        if score >= 6:
            return "PERFECT"
        elif score >= 5:
            return "EXCELLENT"
        elif score >= 4:
            return "STRONG"
        elif score >= 2:
            return "MEDIUM"
        else:
            return "WEAK"
    
    # ==========================================================================
    #                          FORMATTING
    # ==========================================================================
    
    def format_setup(self, setup: TradeSetup) -> str:
        """Форматира setup като текст."""
        lines = [
            "=" * 70,
            f"  TRADE SETUP #{setup.id} - {setup.symbol}",
            f"  {setup.timestamp.strftime('%d.%m.%Y %H:%M')}",
            "=" * 70,
            "",
            f"  Plan:       {setup.plan.value}",
            f"  Bias:       {setup.bias.value} ({setup.confidence}%)",
            f"  Strength:   {setup.signal_strength}",
            "",
            f"  Entry Zone: {setup.entry_zone[0]:.2f} - {setup.entry_zone[1]:.2f}",
            f"  Entry:      {setup.entry_price:.2f}",
            f"  Stop Loss:  {setup.stop_loss:.2f}",
            "",
            "  TARGETS:"
        ]
        
        for t in setup.targets:
            lines.append(f"    {t['name']}: {t['price']:.2f} (Level {t['level']})")
        
        lines.extend([
            "",
            f"  INVALIDATION: {setup.invalidation.get('description', 'N/A')}",
            "",
            "  REASONING:"
        ])
        
        for r in setup.reasoning:
            lines.append(f"    • {r}")
        
        lines.extend([
            "",
            f"  Goldbach Time: {'✓' if setup.goldbach_time_confirm else '✗'}",
            f"  AMD Cycle: {setup.amd_cycle.value}",
            f"  Partition Day: {setup.monthly_partition_day}",
            "",
            "=" * 70
        ])
        
        return "\n".join(lines)


# ==============================================================================
#                              SINGLETON
# ==============================================================================

# Global engine instance
engine = GoldbachEngine()


# ==============================================================================
#                              TEST
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  GOLDBACH UNIFIED ENGINE TEST")
    print("=" * 70)
    
    # Test with NQ price
    test_price = 21500
    
    print(f"\nТест с цена: {test_price}")
    
    # Position info
    pos_info = engine.get_position_info(test_price)
    print(f"\nPO3 Range: {pos_info['range']['low']} - {pos_info['range']['high']}")
    print(f"Position: {pos_info['position_str']}")
    print(f"Layer: {pos_info['layer']}")
    
    # Bias analysis
    bias = engine.analyze_bias(test_price, trend_days=2)
    print(f"\nBias: {bias.bias.value} ({bias.confidence}%)")
    for r in bias.reasoning:
        print(f"  • {r}")
    
    # Goldbach Time
    gb_time = engine.analyze_goldbach_time()
    print(f"\nGoldbach Time: {gb_time.hour}:{gb_time.minute:02d} = {gb_time.sum_value}")
    print(f"  Is Goldbach: {gb_time.is_goldbach}")
    
    # AMD Cycle
    amd = engine.get_amd_cycle()
    print(f"\nAMD Cycle: {amd.cycle_name}")
    print(f"  {amd.trading_bias}")
    
    # Monthly Partition
    partition = engine.get_monthly_partition_info()
    print(f"\nMonthly Partition Day: {partition['partition_day']}")
    if partition['is_key_day']:
        print(f"  KEY DAY: {partition['key_day_info']}")
    
    # Generate Setup
    setup = engine.generate_setup(test_price, "NQ", trend_days=2)
    if setup:
        print("\n" + engine.format_setup(setup))
    else:
        print("\nNo clear setup at current position")
