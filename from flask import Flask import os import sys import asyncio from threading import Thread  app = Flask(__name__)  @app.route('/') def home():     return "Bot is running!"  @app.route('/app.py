from flask import Flask
import os
import sys
import asyncio
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_bot():
    # Импортируй и запускай своего бота здесь
    import bot

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    Thread(target=run_bot).start()
    # Запускаем Flask сервер на порту Render
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
