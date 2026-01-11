# 🎯 GOLDBACH UNIFIED TRADING PLATFORM

Пълна trading платформа комбинираща **Goldbach Trifecta** и **Goldbach Fundamentals** системите.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

## 📋 Съдържание

- [Функции](#-функции)
- [Бърз старт](#-бърз-старт)
- [Инсталация](#-инсталация)
- [Конфигурация](#-конфигурация)
- [Употреба](#-употреба)
- [API Reference](#-api-reference)
- [Backtesting](#-backtesting)
- [Deployment](#-deployment)

---

## ✨ Функции

### 📊 Анализ
- **PO3 Dealing Ranges** - Автоматично изчисляване на ranges (9, 27, 81, 243, 729, 2187, 6561)
- **21 Goldbach Levels** - Всички ключови нива с ICT съответствия
- **3-Layer Framework** - Liquidity, Flow, Rebalance визуализация
- **GIP Bias Detection** - Автоматично определяне на bias

### ⏰ Timing Филтри
- **Goldbach Time** - Real-time проверка Hour + Minute = GB Number
- **AMD Cycles** - Asian, Manipulation, Distribution tracking
- **Monthly Partitions** - Key days и очаквани движения

### 🤖 Автоматизация
- **Signal Generator** - Автоматични trading сигнали
- **Telegram/Discord** - Instant нотификации
- **WebSocket** - Real-time updates

### 📈 Backtesting
- **Historical Testing** - Тест на исторически данни
- **Walk-Forward Analysis** - Robustness проверка
- **Monte Carlo Simulation** - Risk assessment
- **Comprehensive Statistics** - Win rate, Profit Factor, Drawdown, etc.

---

## 🚀 Бърз старт

```bash
# 1. Clone/Extract
cd goldbach_platform

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env with your settings

# 5. Run
python run.py

# 6. Open browser
# http://localhost:5000
```

---

## 📦 Инсталация

### Изисквания
- Python 3.10+
- pip

### Стъпки

```bash
# 1. Създай директория
mkdir goldbach_platform
cd goldbach_platform

# 2. Виртуална среда
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 3. Инсталирай зависимости
pip install -r requirements.txt

# 4. Копирай конфигурация
cp .env.example .env
```

---

## ⚙️ Конфигурация

### .env файл

```env
# Flask
DEBUG=True
SECRET_KEY=your-secret-key

# Server
HOST=0.0.0.0
PORT=5000

# Telegram (Optional)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# Trading
DEFAULT_SYMBOL=NQ
DEFAULT_PO3_SIZE=729
```

### Telegram Setup

1. Отвори Telegram и намери @BotFather
2. Напиши `/newbot` и следвай инструкциите
3. Запиши TOKEN-а
4. Намери Chat ID чрез `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Добави в .env файла

---

## 💻 Употреба

### Dashboard

Отвори `http://localhost:5000` за:
- Quick Analysis - въведи цена и получи пълен анализ
- Levels Visualization - визуализация на Goldbach нивата
- Real-time Timing - Goldbach Time, AMD Cycle, Partition Day
- Signal Generation - автоматични trading сигнали

### Backtest

Отвори `http://localhost:5000/backtest` за:
- Зареждане на исторически данни (JSON/CSV)
- Конфигуриране на backtest параметри
- Изпълнение на backtest
- Преглед на статистика и equity curve
- Monte Carlo simulation

### API

```python
import requests

# Analyze price
response = requests.post('http://localhost:5000/api/analyze', json={
    'price': 21500,
    'symbol': 'NQ',
    'po3_size': 729
})
print(response.json())

# Generate signal
response = requests.post('http://localhost:5000/api/signal', json={
    'price': 21500,
    'symbol': 'NQ',
    'send_notification': True
})
print(response.json())
```

---

## 📡 API Reference

### Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze` | Full price analysis |
| GET | `/api/levels/<range>` | Get Goldbach levels |
| GET | `/api/goldbach-time` | Current Goldbach time |
| GET | `/api/amd-cycle` | Current AMD cycle |
| GET | `/api/partition` | Monthly partition info |

### Signals

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/signal` | Generate signal |
| GET | `/api/signals` | Get signal history |
| GET | `/api/statistics` | Get statistics |

### Backtesting

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/backtest` | Run backtest |
| POST | `/api/backtest/walk-forward` | Walk-forward analysis |

### Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reference/levels` | All Goldbach levels |
| GET | `/api/reference/partitions` | Monthly partitions |
| GET | `/api/reference/plans` | Trade plans |

---

## 📈 Backtesting

### Sample Data Format

```json
[
  {
    "date": "2025-01-01",
    "open": 21000,
    "high": 21100,
    "low": 20900,
    "close": 21050
  },
  ...
]
```

### Configuration Options

```json
{
  "initial_capital": 10000,
  "position_size_pct": 2.0,
  "min_signal_strength": "MEDIUM",
  "po3_size": 729,
  "require_goldbach_time": false,
  "run_monte_carlo": true
}
```

### Statistics Output

- Total Trades / Win Rate
- Total P&L / Profit Factor
- Average Win / Loss
- Max Drawdown
- Risk/Reward Ratio
- Performance by Plan
- Performance by Signal Strength
- Monthly Returns
- Equity Curve

---

## 🚀 Deployment

### Railway (Recommended)

1. Push to GitHub
2. Connect to Railway
3. Add environment variables
4. Deploy

```bash
# Procfile
web: gunicorn -w 2 -b 0.0.0.0:$PORT app.main:app
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app.main:app"]
```

```bash
docker build -t goldbach-platform .
docker run -p 5000:5000 goldbach-platform
```

### VPS

```bash
# Install dependencies
pip install -r requirements.txt

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app.main:app

# Or with supervisor
sudo supervisorctl start goldbach
```

---

## 📚 Goldbach System Reference

### PO3 Sizes

| PO3 | Size | Timeframe |
|-----|------|-----------|
| 3¹ | 9 | 1M |
| 3² | 27 | 5M |
| 3³ | 81 | 15M |
| 3⁴ | 243 | 1H |
| **3⁵** | **729** | **4H/Daily** |
| 3⁶ | 2187 | Weekly |
| 3⁷ | 6561 | Monthly |

### Key Levels

| Level | Name | Layer |
|-------|------|-------|
| [17] | GIP | LIQUIDITY (KEY) |
| [50] | EQ | REBALANCE |
| [83] | GIP | LIQUIDITY (KEY) |

### Trade Plans

1. **EINSTEIN** - GAP entry at [11-17] or [83-89]
2. **LIQUIDITY** - Stop run at extremes
3. **FLOW** - Momentum continuation
4. **REBALANCE** - Range trading

---

## 📝 License

MIT License - Free to use and modify.

---

## 🙏 Credits

Based on **Goldbach Trifecta** and **Goldbach Fundamentals** by **Hopiplaka**.

---

*Happy Trading! 🎯*
