import os
import ccxt
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
import time
import requests

# Render/Koyeb မဟုတ်ဘဲ Cloud Shell မှာသုံးရင် environment variable ကို code ထဲမှာပဲ ခဏထည့်ထားလို့ရပါတယ်
BINANCE_API_KEY = 'G89PG77RtA2SS9JbuiVTYZ9kcbk8cxBvilDIZSolBiAelcE31N8eZAOd7cWufeHC'
BINANCE_SECRET = 'xmLtQ6vCOHINRCtovPKarDDHJ9SxV3le77kHRmPql2SCeGz9LpOgKBENji6KiNtz'
TELEGRAM_TOKEN = '8386199745:AAGpDPB2yYVfGKf4YJlUrWJ-D-zf5KDop5Y'
TELEGRAM_CHAT_ID = '8701531697'

# ... (ကျန်တဲ့ Bot Code အကုန်လုံးကို အောက်မှာ ဆက်ထည့်ပါ)
# ==========================================
# ၂။ Bot Settings (Hyper-Compounding)
# ==========================================
symbols = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'TRX/USDT', 'LINK/USDT',
    'DOT/USDT', 'MATIC/USDT', 'SHIB/USDT', 'LTC/USDT', 'BCH/USDT',
    'NEAR/USDT', 'UNI/USDT', 'ICP/USDT', 'FIL/USDT', 'APT/USDT'
]
LEVERAGE = 10
RISK_PER_TRADE = 0.2  # လက်ကျန်ငွေ၏ ၂၀% ကို အသုံးပြုမည်
TP_PERCENT = 0.015    # 1.5% အမြတ်ရယူမည်
SL_PERCENT = 0.007    # 0.7% အရှုံးခံမည်

# Binance Futures ချိတ်ဆက်ခြင်း
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
    except: pass

# ==========================================
# ၃။ Feature Engineering & Training
# ==========================================
def prepare_indicators(df):
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['vol_surge'] = df['volume'] / (df['volume'].rolling(20).mean() + 1e-9)
    df['rsi'] = 100 - (100 / (1 + (df['close'].diff().where(df['close'].diff() > 0, 0).rolling(14).mean() / 
                                  (-df['close'].diff().where(df['close'].diff() < 0, 0).rolling(14).mean() + 1e-9))))
    return df.dropna()

def train_model():
    all_data = []
    send_telegram("⏳ *ဈေးကွက်ဒေတာများကို စတင်လေ့လာနေပါသည်...*")
    
    for symbol in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=1000)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = prepare_indicators(df)
            df['target'] = np.where(df['close'].shift(-5) > (df['close'] * 1.015), 1, 0)
            all_data.append(df.dropna())
        except: continue
            
    if not all_data:
            print("⚠️ Binance ဆီမှ ဒေတာ မရရှိပါ။ IP Whitelist ကို စစ်ဆေးပါ။")
            return None  # Error မတက်အောင် ကျော်ခိုင်းလိုက်တာပါ    
    final_df = pd.concat(all_data)
    features = ['ema_200', 'vol_surge', 'rsi', 'close']
    model = XGBClassifier(n_estimators=1000, max_depth=8, learning_rate=0.01)
    model.fit(final_df[features], final_df['target'])
    send_telegram("✅ *Model Training ပြီးစီးပါပြီ။* \nBot စတင်လည်ပတ်နေပါပြီ။")
    return model

# ==========================================
# ၄။ Trading Execution Loop
# ==========================================
def run_bot():
    model = train_model()
    active_trades = {}

    while True:
        try:
            balance_info = exchange.fetch_balance()
            total_balance = float(balance_info['total']['USDT'])
        except:
            time.sleep(10); continue

        for symbol in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df = prepare_indicators(df)
                last_row = df.iloc[[-1]]
                
                prob = model.predict_proba(last_row[['ema_200', 'vol_surge', 'rsi', 'close']])[0][1]
                current_price = last_row['close'].values[0]

                # Buy Signal စစ်ဆေးခြင်း
                if prob > 0.65 and symbol not in active_trades:
                    trade_amount = total_balance * RISK_PER_TRADE * LEVERAGE
                    qty = trade_amount / current_price
                    
                    # တကယ်အော်ဒါဖွင့်ရန် အောက်ပါ line ကို ဖွင့်ပေးပါ
                    # exchange.create_market_buy_order(symbol, qty)
                    
                    active_trades[symbol] = {'entry_price': current_price, 'qty': qty}
                    send_telegram(f"🟢 *ဝယ်ယူမှု (BUY)* \n📍 Coin: {symbol} \n💰 ဈေးနှုန်း: {current_price} \n💵 လက်ကျန်ငွေ: ${total_balance:.2f}")

                # Take Profit / Stop Loss စစ်ဆေးခြင်း
                if symbol in active_trades:
                    entry = active_trades[symbol]['entry_price']
                    price_change = (current_price - entry) / entry
                    
                    if price_change >= TP_PERCENT:
                        # exchange.create_market_sell_order(symbol, active_trades[symbol]['qty'])
                        del active_trades[symbol]
                        send_telegram(f"💰 *အမြတ်ရယူခြင်း (PROFIT)* \n📍 Coin: {symbol} \n📈 အမြတ်: +{(price_change*100*LEVERAGE):.2f}%")
                        
                    elif price_change <= -SL_PERCENT:
                        # exchange.create_market_sell_order(symbol, active_trades[symbol]['qty'])
                        del active_trades[symbol]
                        send_telegram(f"🛑 *အရှုံးရပ်တန့်ခြင်း (STOP LOSS)* \n📍 Coin: {symbol} \n📉 အရှုံး: -{(abs(price_change)*100*LEVERAGE):.2f}%")

            except Exception as e:
                print(f"Error {symbol}: {e}")
        
        time.sleep(300) # ၅ မိနစ်တစ်ခါ စစ်ဆေးမည်

if __name__ == "__main__":
    run_bot()
