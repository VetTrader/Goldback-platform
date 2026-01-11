#!/usr/bin/env python3
"""
================================================================================
                    GOLDBACH UNIFIED TRADING PLATFORM
                    Entry Point
================================================================================

Стартиране:
    python run.py                    # Development mode
    gunicorn -w 2 app.main:app      # Production mode

Environment Variables:
    DEBUG=True/False
    HOST=0.0.0.0
    PORT=5000
    SECRET_KEY=your-secret-key
    TELEGRAM_BOT_TOKEN=your-bot-token
    TELEGRAM_CHAT_ID=your-chat-id

================================================================================
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import app
from app.main import app, socketio, config

def print_banner():
    """Print startup banner."""
    print("=" * 70)
    print("""
   ██████╗  ██████╗ ██╗     ██████╗ ██████╗  █████╗  ██████╗██╗  ██╗
  ██╔════╝ ██╔═══██╗██║     ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║  ██║
  ██║  ███╗██║   ██║██║     ██║  ██║██████╔╝███████║██║     ███████║
  ██║   ██║██║   ██║██║     ██║  ██║██╔══██╗██╔══██║██║     ██╔══██║
  ╚██████╔╝╚██████╔╝███████╗██████╔╝██████╔╝██║  ██║╚██████╗██║  ██║
   ╚═════╝  ╚═════╝ ╚══════╝╚═════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
    """)
    print("                 UNIFIED TRADING PLATFORM v1.0")
    print("          Trifecta + Fundamentals | By Hopiplaka")
    print("=" * 70)
    print()
    print(f"    🌐 Server:     http://{config.HOST}:{config.PORT}")
    print(f"    📊 Dashboard:  http://{config.HOST}:{config.PORT}/")
    print(f"    🧪 Backtest:   http://{config.HOST}:{config.PORT}/backtest")
    print(f"    📡 Signals:    http://{config.HOST}:{config.PORT}/signals")
    print(f"    📚 Docs:       http://{config.HOST}:{config.PORT}/docs")
    print()
    print(f"    🔧 Debug Mode: {config.DEBUG}")
    print(f"    📱 Telegram:   {'Configured' if config.TELEGRAM_BOT_TOKEN else 'Not configured'}")
    print()
    print("=" * 70)
    print()


def main():
    """Main entry point."""
    print_banner()
    
    # Create data directory if needed
    os.makedirs('data', exist_ok=True)
    
    # Run with SocketIO
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=config.DEBUG,
        log_output=True
    )


if __name__ == '__main__':
    main()
