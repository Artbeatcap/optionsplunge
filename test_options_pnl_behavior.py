import requests
import json
from datetime import datetime, timedelta

# Adjust as needed for your local server
BASE_URL = 'http://127.0.0.1:5000/tools/options-pnl'

# Simulate login (if needed, otherwise use session/cookie)
# For now, assume already logged in or use a test client

def test_options_pnl(option_type):
    today = datetime.now().date()
    expiration = today + timedelta(days=30)
    data = {
        'option_type': option_type,  # 'call' or 'put'
        'strike': 195.0,
        'current_price': 195.0,
        'expiration_date': expiration.strftime('%Y-%m-%d'),
        'premium': 3.50,
        'quantity': 1
    }
    print(f"\n=== Testing {option_type.upper()} ===")
    resp = requests.post(BASE_URL, json=data)
    try:
        result = resp.json()
    except Exception as e:
        print(f"Error parsing JSON: {e}\nResponse: {resp.text}")
        return
    if not result.get('success'):
        print(f"Error: {result.get('error')}")
        return
    analysis = result['analysis']
    print(f"Implied Volatility: {analysis['option_details']['implied_volatility']}%")
    print(f"Scenario Analysis Table:")
    for row in analysis['scenario_analysis']:
        print(row)
    print(f"\nChart Data (Current Price P&L for each timeframe):")
    price_range = analysis['chart_data']['price_range']
    idx_current = min(range(len(price_range)), key=lambda i: abs(price_range[i] - 195.0))
    for tf in analysis['chart_data']['timeframes']:
        label = tf['label']
        pnl = tf['pnl_curve'][idx_current]
        print(f"  {label}: P&L at current price = ${pnl}")

test_options_pnl('call')
test_options_pnl('put') 