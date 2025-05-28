import app_original
from datetime import datetime
import numpy as np

# Get options chain for NFLX 1200C expiring 2025-05-30
calls, puts, price, expirations = app_original.get_options_chain_tradier('NFLX', '2025-05-30')
call = calls[calls['strike'] == 1200]
if not call.empty:
    last = float(call.iloc[0]['last'])
    print(f'NFLX 1200C last: {last}')
    S = price
    K = 1200
    today = datetime.now()
    expiry = datetime(2025,5,30)
    total_days = (expiry - today).days
    intrinsic_at_expiry = max(S - K, 0)
    print(f'Total days to expiry: {total_days}')
    # Show value for 30, 15, 7, 1, 0 days left
    for days_left in [30, 15, 7, 1, 0]:
        if days_left >= total_days:
            option_value = last
        elif days_left <= 0:
            option_value = intrinsic_at_expiry
        else:
            # Linear interpolation between last and intrinsic value
            option_value = last * (days_left / total_days) + intrinsic_at_expiry * (1 - days_left / total_days)
        pnl = (option_value - last) * 100
        print(f'Days left: {days_left}, Interpolated Value: {option_value:.2f}, Intrinsic: {intrinsic_at_expiry:.2f}, PnL: {pnl:.2f}')
else:
    print('No 1200C found') 