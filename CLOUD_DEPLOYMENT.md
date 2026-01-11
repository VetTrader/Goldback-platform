# ☁️ CLOUD DEPLOYMENT GUIDE
# Goldbach Trading Platform

Това ръководство обяснява как да инсталираш платформата на cloud сървър за 24/7 достъп отвсякъде.

---

## 📋 Съдържание

1. [Избор на платформа](#1-избор-на-платформа)
2. [Railway (Препоръчително)](#2-railway-препоръчително)
3. [Render](#3-render)
4. [DigitalOcean](#4-digitalocean)
5. [Docker Deployment](#5-docker-deployment)
6. [TradingView Integration](#6-tradingview-integration)
7. [Data Provider Setup](#7-data-provider-setup)
8. [Telegram Bot Setup](#8-telegram-bot-setup)

---

## 1. Избор на платформа

| Платформа | Цена | Трудност | Предимства |
|-----------|------|----------|------------|
| **Railway** | $5/мес | ⭐ Лесно | Най-лесен deploy, GitHub интеграция |
| **Render** | $7/мес | ⭐ Лесно | Добър free tier |
| **DigitalOcean** | $4-6/мес | ⭐⭐ Средно | Пълен контрол |
| **Heroku** | $5-7/мес | ⭐ Лесно | Популярен, много ресурси |
| **VPS (Hetzner)** | €3/мес | ⭐⭐⭐ Сложно | Най-евтин, пълен контрол |

**Препоръка:** Започни с **Railway** - най-лесният вариант!

---

## 2. Railway (Препоръчително)

### Стъпка 1: Подготовка
1. Създай акаунт в https://railway.app (може с GitHub)
2. Качи кода в GitHub repository

### Стъпка 2: Deploy
```bash
# В терминала (в папката на проекта)
railway login
railway init
railway up
```

**Или през браузъра:**
1. Отиди на https://railway.app/new
2. Избери "Deploy from GitHub repo"
3. Избери твоето repository
4. Railway автоматично ще открие Procfile и ще deploy-не

### Стъпка 3: Environment Variables
В Railway dashboard → твоя проект → Variables:

```
SECRET_KEY=random-secret-string-here
DEBUG=False
TELEGRAM_BOT_TOKEN=твоя-telegram-token
TELEGRAM_CHAT_ID=твоя-chat-id
TWELVEDATA_API_KEY=твоя-api-key
SYMBOLS=NQ,ES,EURUSD
ENABLE_SCHEDULER=True
```

### Стъпка 4: Custom Domain (по избор)
1. Settings → Domains
2. Добави custom domain или използвай railway.app subdomain

**Цена:** $5/месец за Hobby план (500 часа/месец free)

---

## 3. Render

### Стъпка 1: Подготовка
1. Създай акаунт в https://render.com
2. Качи кода в GitHub

### Стъпка 2: Create Web Service
1. Dashboard → New → Web Service
2. Connect GitHub repository
3. Settings:
   - **Name:** goldbach-platform
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -w 2 -b 0.0.0.0:$PORT app.main:app`

### Стъпка 3: Environment Variables
В Environment tab добави същите променливи като за Railway.

**Цена:** Free tier (спира при неактивност), $7/месец за постоянен

---

## 4. DigitalOcean

### Стъпка 1: Create Droplet
1. https://cloud.digitalocean.com
2. Create → Droplets
3. Избери:
   - **Image:** Ubuntu 22.04
   - **Size:** Basic $4/месец (1GB RAM)
   - **Region:** Frankfurt (най-близо до България)

### Стъпка 2: Setup сървъра
```bash
# SSH към сървъра
ssh root@твоя-ip

# Update системата
apt update && apt upgrade -y

# Инсталирай Python
apt install python3.11 python3.11-venv python3-pip git nginx -y

# Clone проекта
git clone https://github.com/твоя-repo/goldbach-platform.git
cd goldbach-platform

# Setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Create .env
cp .env.example .env
nano .env  # редактирай настройките

# Test
python run.py
```

### Стъпка 3: Setup systemd service
```bash
# Създай service файл
sudo nano /etc/systemd/system/goldbach.service
```

```ini
[Unit]
Description=Goldbach Trading Platform
After=network.target

[Service]
User=root
WorkingDirectory=/root/goldbach-platform
Environment="PATH=/root/goldbach-platform/venv/bin"
ExecStart=/root/goldbach-platform/venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app.main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Активирай и стартирай
sudo systemctl daemon-reload
sudo systemctl enable goldbach
sudo systemctl start goldbach
sudo systemctl status goldbach
```

### Стъпка 4: Setup Nginx
```bash
sudo nano /etc/nginx/sites-available/goldbach
```

```nginx
server {
    listen 80;
    server_name твоя-домейн.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/goldbach /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### Стъпка 5: SSL Certificate (HTTPS)
```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d твоя-домейн.com
```

---

## 5. Docker Deployment

### Local Docker
```bash
# Build и стартирай
docker-compose up -d

# Провери логове
docker-compose logs -f

# Спри
docker-compose down
```

### Cloud Docker (DigitalOcean, AWS, etc.)
```bash
# На сървъра
apt install docker.io docker-compose -y

# Clone и стартирай
git clone https://github.com/твоя-repo/goldbach-platform.git
cd goldbach-platform
cp .env.example .env
nano .env  # редактирай

docker-compose up -d
```

---

## 6. TradingView Integration

### Автоматични alerts от TradingView

1. **Вземи твоя webhook URL:**
   ```
   https://твоя-домейн.com/api/webhook/tradingview
   ```

2. **В TradingView:**
   - Създай Alert на желания индикатор/стратегия
   - Notification → Webhook URL → твоя URL
   - Message format:
   ```json
   {
     "symbol": "{{ticker}}",
     "price": {{close}},
     "action": "{{strategy.order.action}}",
     "time": "{{time}}",
     "interval": "{{interval}}"
   }
   ```

3. **Optional: Secret key**
   - Добави `TRADINGVIEW_WEBHOOK_SECRET=твоя-тайна` в .env
   - В TradingView добави header: `X-TV-Secret: твоя-тайна`

### Pine Script Alert Example
```pine
//@version=5
strategy("Goldbach Webhook", overlay=true)

// Твоята стратегия...

if (buyCondition)
    strategy.entry("Long", strategy.long, alert_message='{"symbol":"{{ticker}}","price":{{close}},"action":"buy"}')

if (sellCondition)
    strategy.entry("Short", strategy.short, alert_message='{"symbol":"{{ticker}}","price":{{close}},"action":"sell"}')
```

---

## 7. Data Provider Setup

### Yahoo Finance (Default - Free)
- Не изисква API key
- Автоматично активен
- Delay: 15-20 минути

### Twelve Data (Препоръчително)
1. Регистрирай се: https://twelvedata.com/
2. Вземи API key от dashboard
3. Добави в .env:
   ```
   TWELVEDATA_API_KEY=твоя-api-key
   ```
4. Free tier: 800 calls/ден, 8/минута

### Polygon.io (US Stocks)
1. Регистрирай се: https://polygon.io/
2. Вземи API key
3. Добави в .env:
   ```
   POLYGON_API_KEY=твоя-api-key
   ```

---

## 8. Telegram Bot Setup

### Стъпка 1: Създай бот
1. Отвори Telegram
2. Намери @BotFather
3. Напиши `/newbot`
4. Следвай инструкциите
5. Запиши TOKEN-а

### Стъпка 2: Вземи Chat ID
1. Отвори бота си и напиши нещо
2. Отвори в браузъра:
   ```
   https://api.telegram.org/bot<ТВОЯ_TOKEN>/getUpdates
   ```
3. Намери `"chat":{"id": ЧИСЛО}` - това е твоя Chat ID

### Стъпка 3: Добави в .env
```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321
```

### Стъпка 4: Тествай
```bash
curl -X POST "https://твоя-домейн.com/api/signal" \
     -H "Content-Type: application/json" \
     -d '{"price": 21500, "symbol": "NQ", "send_notification": true}'
```

---

## 🔧 Troubleshooting

### Проблем: Scheduler не работи
```bash
# Провери логове
docker-compose logs goldbach | grep -i scheduler

# Или на VPS
journalctl -u goldbach -f
```

### Проблем: Няма данни от Yahoo
- Yahoo има rate limits
- Провери дали символът е правилен (NQ=F за futures)

### Проблем: TradingView webhook не работи
- Провери дали URL-а е достъпен отвън
- Провери firewall/nginx конфигурация
- Провери логовете за грешки

---

## 📊 Мониторинг

### UptimeRobot (Free)
1. https://uptimerobot.com
2. Add Monitor → HTTP(s)
3. URL: `https://твоя-домейн.com/health`
4. Interval: 5 minutes

### Логове
```bash
# Railway
railway logs

# Docker
docker-compose logs -f

# Systemd
journalctl -u goldbach -f
```

---

## 🎯 Готово!

След deployment ще имаш:
- ✅ 24/7 работеща платформа
- ✅ Достъп отвсякъде през браузър
- ✅ Автоматични анализи по график
- ✅ TradingView webhook интеграция
- ✅ Telegram/Discord нотификации
- ✅ Real-time data feeds

**URL-ове:**
- Dashboard: `https://твоя-домейн.com/`
- Backtest: `https://твоя-домейн.com/backtest`
- API: `https://твоя-домейн.com/api/`
- Health: `https://твоя-домейн.com/health`

---

*Въпроси? Проблеми? Провери логовете първо!*
