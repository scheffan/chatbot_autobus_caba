import os, argparse, asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv(); TOKEN=os.getenv('TELEGRAM_BOT_TOKEN')
def main():
 p=argparse.ArgumentParser(); p.add_argument('--url', required=True)
 a=p.parse_args()
 if not TOKEN: print('Falta TELEGRAM_BOT_TOKEN'); return
 bot=Bot(TOKEN); asyncio.run(bot.set_webhook(a.url)); print('Webhook seteado:', a.url)
if __name__=='__main__': main()
