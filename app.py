from flask import Flask
import threading
from bot import Client

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

@app.route('/health')
def health_check():
    return 'OK', 200

def run_bot():
    Client.run()

if __name__ == '__main__':
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    # Run the Flask app
    app.run(host='0.0.0.0', port=8080)
