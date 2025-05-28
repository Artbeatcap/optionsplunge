from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, User, Trade, TradeAnalysis, TradingJournal, UserSettings
from forms import (LoginForm, RegistrationForm, TradeForm, QuickTradeForm, 
                   JournalForm, EditTradeForm, UserSettingsForm, BulkAnalysisForm)
from ai_analysis import TradingAIAnalyzer
from datetime import datetime, timedelta, date
import pandas as pd
import plotly.graph_objs as go
import plotly.utils
import json
import os
import secrets
import requests
import yfinance as yf
import numpy as np
from scipy.stats import norm
import math
from werkzeug.utils import secure_filename

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Environment variables loaded from .env file")
except ImportError:
    print("python-dotenv not installed, using system environment variables")
    pass
except Exception as e:
    print(f"Error loading .env file: {e}, using fallback configuration")
    pass

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Initialize AI analyzer
ai_analyzer = TradingAIAnalyzer()

# Tradier API configuration
TRADIER_API_BASE = "https://api.tradier.com/v1"  # Use production API
# For sandbox testing, use: "https://sandbox.tradier.com/v1"

# Load Tradier token - using direct assignment to bypass .env issues temporarily
TRADIER_TOKEN = "fImjhesSMVWnq15UN5PWUvARApRX"  # Your actual token
print(f"Tradier token configured: {'Yes' if TRADIER_TOKEN != 'your_tradier_token_here' else 'No'}")
print(f"Using Tradier API endpoint: {TRADIER_API_BASE}")

def get_tradier_headers():
    """Get headers for Tradier API requests"""
    if TRADIER_TOKEN == 'your_tradier_token_here' or not TRADIER_TOKEN:
        return None  # Token not configured
    
    return {
        'Authorization': f'Bearer {TRADIER_TOKEN}',
        'Accept': 'application/json'
    }

def get_options_chain_tradier(symbol, expiration_date=None):
    """Get options chain data using Tradier API"""
    try:
        headers = get_tradier_headers()
        if not headers:
            print("Tradier API token not configured, skipping Tradier API call")
            return None, None, None, None

        print(f"Fetching options data for {symbol} using Tradier API...")
        
        # First get available expiration dates
        exp_url = f"{TRADIER_API_BASE}/markets/options/expirations"
        exp_params = {'symbol': symbol}
        
        print(f"Getting expirations from: {exp_url}")
        exp_response = requests.get(exp_url, params=exp_params, headers=headers)
        
        print(f"Expiration response status: {exp_response.status_code}")
        if exp_response.status_code != 200:
            print(f"Error getting expirations for {symbol}: {exp_response.status_code}")
            print(f"Response content: {exp_response.text[:500]}")
            return None, None, None, None
        
        exp_data = exp_response.json()
        print(f"Expiration data keys: {list(exp_data.keys()) if exp_data else 'None'}")
        
        if 'expirations' not in exp_data or not exp_data['expirations']:
            print(f"No expirations found for {symbol}")
            print(f"Response: {exp_data}")
            return None, None, None, None
            
        expirations = exp_data['expirations']['date']
        if isinstance(expirations, str):
            expirations = [expirations]
        
        print(f"Found {len(expirations)} expiration dates for {symbol}: {expirations[:3]}...")
        
        # Use provided expiration or first available
        target_date = expiration_date if expiration_date and expiration_date in expirations else expirations[0]
        print(f"Using expiration date: {target_date}")
        
        # Get options chain for the target date
        chain_url = f"{TRADIER_API_BASE}/markets/options/chains"
        chain_params = {
            'symbol': symbol,
            'expiration': target_date
        }
        
        print(f"Getting options chain from: {chain_url} with params: {chain_params}")
        chain_response = requests.get(chain_url, params=chain_params, headers=headers)
        
        print(f"Options chain response status: {chain_response.status_code}")
        if chain_response.status_code != 200:
            print(f"Error getting options chain for {symbol}: {chain_response.status_code}")
            print(f"Response content: {chain_response.text[:500]}")
            return None, None, None, None
        
        chain_data = chain_response.json()
        print(f"Chain data keys: {list(chain_data.keys()) if chain_data else 'None'}")
        
        if 'options' not in chain_data or not chain_data['options']:
            print(f"No options data for {symbol} on {target_date}")
            print(f"Response: {chain_data}")
            return None, None, None, None
        
        options = chain_data['options']['option']
        if not isinstance(options, list):
            options = [options]
        
        print(f"Found {len(options)} options for {symbol}")
        
        # Separate calls and puts
        calls_data = []
        puts_data = []
        
        for option in options:
            option_data = {
                'strike': float(option['strike']),
                'last': float(option.get('last', 0)) if option.get('last') else 0,
                'bid': float(option.get('bid', 0)) if option.get('bid') else 0,
                'ask': float(option.get('ask', 0)) if option.get('ask') else 0,
                'volume': int(option.get('volume', 0)) if option.get('volume') else 0,
                'open_interest': int(option.get('open_interest', 0)) if option.get('open_interest') else 0,
                'implied_volatility': float(option.get('greeks', {}).get('mid_iv', 0)) if option.get('greeks') else 0
            }
            
            if option['option_type'] == 'call':
                calls_data.append(option_data)
            else:
                puts_data.append(option_data)
        
        print(f"Processed {len(calls_data)} calls and {len(puts_data)} puts")
        
        # Convert to DataFrames for compatibility
        calls_df = pd.DataFrame(calls_data) if calls_data else pd.DataFrame()
        puts_df = pd.DataFrame(puts_data) if puts_data else pd.DataFrame()
        
        # Get current stock price
        current_price = get_stock_price_tradier(symbol)
        print(f"Current price for {symbol}: {current_price}")
        
        return calls_df, puts_df, current_price, expirations
        
    except Exception as e:
        print(f"Error fetching options data from Tradier for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None

def get_stock_price_tradier(symbol):
    """Get current stock price using Tradier API"""
    try:
        headers = get_tradier_headers()
        if not headers:
            print("No Tradier headers available")
            return None
            
        url = f"{TRADIER_API_BASE}/markets/quotes"
        params = {'symbols': symbol}
        
        print(f"Getting stock price for {symbol} from: {url}")
        response = requests.get(url, params=params, headers=headers)
        
        print(f"Stock price response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error getting stock price: {response.text[:500]}")
            return None
        
        data = response.json()
        print(f"Stock price data keys: {list(data.keys()) if data else 'None'}")
        
        if 'quotes' in data and 'quote' in data['quotes']:
            quote = data['quotes']['quote']
            if isinstance(quote, list):
                quote = quote[0]
            price = float(quote.get('last', 0))
            print(f"Extracted price for {symbol}: {price}")
            return price
        
        print(f"No valid price data in response: {data}")
        return None
        
    except Exception as e:
        print(f"Error getting stock price from Tradier for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_options_chain(symbol, expiration_date=None):
    """Get options chain data using Tradier API only (no Yahoo Finance fallback)"""
    try:
        print(f"Getting options chain for {symbol} using Tradier API only...")
        
        # Use Tradier API only
        calls, puts, current_price, expirations = get_options_chain_tradier(symbol, expiration_date)
        
        if calls is not None and puts is not None:
            print(f"Successfully retrieved options data for {symbol}")
            return calls, puts, current_price
        else:
            print(f"Failed to get options data for {symbol} from Tradier API")
            return None, None, None
        
    except Exception as e:
        print(f"Error in get_options_chain for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def black_scholes(S, K, T, r, sigma, option_type='call'):
    """Calculate Black-Scholes option price"""
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == 'call':
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:  # put
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
        return max(price, 0)
    except:
        return 0

def calculate_greeks(S, K, T, r, sigma, option_type='call'):
    """Calculate option Greeks"""
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        # Delta
        if option_type == 'call':
            delta = norm.cdf(d1)
        else:
            delta = norm.cdf(d1) - 1
        
        # Gamma
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        
        # Theta
        if option_type == 'call':
            theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) 
                    - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
        else:
            theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) 
                    + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
        
        # Vega
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100
        
        return {
            'delta': round(delta, 4),
            'gamma': round(gamma, 4),
            'theta': round(theta, 4),
            'vega': round(vega, 4)
        }
    except:
        return {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file, prefix="chart"):
    """Save uploaded file with secure filename"""
    if file and allowed_file(file.filename):
        # Generate secure filename with random suffix
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        unique_filename = f"{prefix}_{secrets.token_hex(8)}{ext}"
        
        # Create uploads directory if it doesn't exist
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'])
        os.makedirs(upload_path, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_path, unique_filename)
        file.save(file_path)
        return unique_filename
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
@login_required
def home():
    """Authenticated user homepage with quick access to features"""
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Welcome back!', 'success')
            return redirect(url_for('index'))
        flash('Invalid username or password', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        # Create default settings
        settings = UserSettings(user_id=user.id)
        db.session.add(settings)
        db.session.commit()
        
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not current_user.is_authenticated:
        # Show empty stats and no trades/journals for guests
        stats = {
            'total_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'trades_analyzed': 0
        }
        return render_template('dashboard.html', 
                             recent_trades=None,
                             stats=stats,
                             recent_journals=None,
                             today_journal=None)
    # Authenticated user: show real data
    update_open_positions_pnl(current_user.id)
    recent_trades = current_user.get_recent_trades(10)
    stats = {
        'total_trades': Trade.query.filter_by(user_id=current_user.id).count(),
        'win_rate': current_user.get_win_rate(),
        'total_pnl': current_user.get_total_pnl(),
        'trades_analyzed': Trade.query.filter_by(user_id=current_user.id, is_analyzed=True).count()
    }
    recent_journals = TradingJournal.query.filter_by(user_id=current_user.id)\
                                         .order_by(TradingJournal.journal_date.desc())\
                                         .limit(5).all()
    today_journal = TradingJournal.query.filter_by(
        user_id=current_user.id, 
        journal_date=date.today()
    ).first()
    return render_template('dashboard.html', 
                         recent_trades=recent_trades,
                         stats=stats,
                         recent_journals=recent_journals,
                         today_journal=today_journal)

def update_open_positions_pnl(user_id):
    """Update P&L for all open positions using current market prices"""
    open_trades = Trade.query.filter_by(user_id=user_id)\
                            .filter(Trade.exit_price.is_(None))\
                            .all()
    
    for trade in open_trades:
        try:
            # Check if trade was entered recently (within last 2 hours)
            time_since_entry = datetime.now() - trade.entry_date
            is_recent_trade = time_since_entry.total_seconds() < 7200  # 2 hours
            
            if trade.is_option_trade():
                # For options, get current stock price first to check underlying movement
                current_stock_price = get_stock_price_tradier(trade.symbol)
                
                # Check underlying stock price movement
                if trade.underlying_price_at_entry and current_stock_price:
                    stock_price_change = abs(current_stock_price - trade.underlying_price_at_entry)
                    stock_change_percent = stock_price_change / trade.underlying_price_at_entry if trade.underlying_price_at_entry > 0 else 0
                    
                    # If recent trade OR underlying stock hasn't moved significantly (< 2%), set P&L to zero
                    if is_recent_trade or stock_change_percent < 0.02:
                        trade.profit_loss = 0.0
                        trade.profit_loss_percent = 0.0
                        print(f"Setting options P&L to zero for {trade.symbol}: {'Recent trade' if is_recent_trade else f'Stock movement only {stock_change_percent*100:.1f}%'}")
                        continue
                
                # Only calculate option P&L if stock has moved significantly
                if trade.expiration_date:
                    exp_date_str = trade.expiration_date.strftime('%Y-%m-%d')
                    calls, puts, current_stock_price = get_options_chain(trade.symbol, exp_date_str)
                    
                    current_option_price = None
                    if calls is not None and puts is not None and trade.strike_price:
                        # Find the specific option in the chain
                        if trade.trade_type == 'option_call' and hasattr(calls, 'empty') and not calls.empty:
                            matching_option = calls[calls['strike'] == trade.strike_price]
                            if not matching_option.empty:
                                row = matching_option.iloc[0]
                                # Use last price if available, otherwise use midpoint of bid/ask
                                current_option_price = row.get('last', 0)
                                if not current_option_price or current_option_price <= 0:
                                    bid = row.get('bid', 0)
                                    ask = row.get('ask', 0)
                                    if bid > 0 and ask > 0:
                                        current_option_price = (bid + ask) / 2
                        
                        elif trade.trade_type == 'option_put' and hasattr(puts, 'empty') and not puts.empty:
                            matching_option = puts[puts['strike'] == trade.strike_price]
                            if not matching_option.empty:
                                row = matching_option.iloc[0]
                                # Use last price if available, otherwise use midpoint of bid/ask
                                current_option_price = row.get('last', 0)
                                if not current_option_price or current_option_price <= 0:
                                    bid = row.get('bid', 0)
                                    ask = row.get('ask', 0)
                                    if bid > 0 and ask > 0:
                                        current_option_price = (bid + ask) / 2
                    
                    # Calculate P&L only when we have significant stock movement
                    if current_option_price and current_option_price > 0:
                        unrealized_pnl = (current_option_price - trade.entry_price) * trade.quantity * 100
                        cost_basis = trade.entry_price * trade.quantity * 100
                        unrealized_pnl_percent = (unrealized_pnl / cost_basis) * 100 if cost_basis > 0 else 0
                        
                        trade.profit_loss = unrealized_pnl
                        trade.profit_loss_percent = unrealized_pnl_percent
                        
                        print(f"Updated option P&L for {trade.symbol}: Stock moved from ${trade.underlying_price_at_entry} to ${current_stock_price}, Option P&L=${unrealized_pnl:.2f}")
                    else:
                        # No current option price available, keep P&L at 0
                        trade.profit_loss = 0.0
                        trade.profit_loss_percent = 0.0
                        print(f"No current option price for {trade.symbol} ${trade.strike_price} {trade.trade_type}")
                else:
                    # No expiration date, can't get options chain
                    trade.profit_loss = 0.0
                    trade.profit_loss_percent = 0.0
            else:
                # For stocks, get current stock price
                current_stock_price = get_stock_price_tradier(trade.symbol)
                if current_stock_price and current_stock_price != trade.entry_price:
                    price_difference = abs(current_stock_price - trade.entry_price)
                    price_change_percent = price_difference / trade.entry_price if trade.entry_price > 0 else 0
                    
                    # If trade is recent OR price difference is minimal (< 1%), set P&L to zero
                    if is_recent_trade or price_change_percent < 0.01:
                        trade.profit_loss = 0.0
                        trade.profit_loss_percent = 0.0
                        print(f"Setting stock P&L to zero for {trade.symbol}: {'Recent trade' if is_recent_trade else 'Minimal price change'}")
                    else:
                        # Calculate normal P&L for older trades with significant price movement
                        if trade.trade_type == 'long':
                            unrealized_pnl = (current_stock_price - trade.entry_price) * trade.quantity
                        elif trade.trade_type == 'short':
                            unrealized_pnl = (trade.entry_price - current_stock_price) * trade.quantity
                        else:
                            continue
                        
                        cost_basis = trade.entry_price * trade.quantity
                        unrealized_pnl_percent = (unrealized_pnl / cost_basis) * 100 if cost_basis > 0 else 0
                        
                        trade.profit_loss = unrealized_pnl
                        trade.profit_loss_percent = unrealized_pnl_percent
                        
                        print(f"Updated stock P&L for {trade.symbol}: Entry=${trade.entry_price}, Current=${current_stock_price}, P&L=${unrealized_pnl:.2f}")
                else:
                    # Keep P&L at 0 if no price change or price unavailable
                    trade.profit_loss = 0.0
                    trade.profit_loss_percent = 0.0
                    
        except Exception as e:
            print(f"Error updating P&L for trade {trade.id}: {e}")
            # Set to 0 instead of showing incorrect values
            trade.profit_loss = 0.0
            trade.profit_loss_percent = 0.0
    
    # Save all updates
    try:
        db.session.commit()
    except Exception as e:
        print(f"Error saving P&L updates: {e}")
        db.session.rollback()

@app.route('/trades')
@login_required
def trades():
    # Update open positions with current market prices
    update_open_positions_pnl(current_user.id)
    
    page = request.args.get('page', 1, type=int)
    trades = Trade.query.filter_by(user_id=current_user.id)\
                       .order_by(Trade.entry_date.desc())\
                       .paginate(
                           page=page, 
                           per_page=20, 
                           error_out=False
                       )
    return render_template('trades.html', trades=trades)

def create_or_update_journal_from_trade(trade):
    """Create or update journal entry template based on trade information"""
    trade_date = trade.entry_date.date()
    
    # Check if journal entry already exists for this day
    journal = TradingJournal.query.filter_by(
        user_id=current_user.id,
        journal_date=trade_date
    ).first()
    
    # Create template content based on trade
    setup_description = f"Entered {trade.symbol} {trade.trade_type.replace('_', ' ').title()}"
    if trade.setup_type:
        setup_description += f" - {trade.setup_type} setup"
    if trade.market_condition:
        setup_description += f" in {trade.market_condition.replace('_', ' ')} market conditions"
    
    # Create entry reason template
    entry_template = ""
    if trade.entry_reason:
        entry_template = f"Trade Rationale: {trade.entry_reason}\n\n"
    
    # Create market outlook template
    market_template = ""
    if trade.market_condition:
        condition_desc = trade.market_condition.replace('_', ' ').title()
        market_template = f"Market appeared to be {condition_desc.lower()}. "
    
    # Add options-specific context
    if trade.is_option_trade():
        if trade.expiration_date:
            days_to_exp = (trade.expiration_date - trade_date).days
            entry_template += f"Options Trade: {trade.option_type.title()} option with {days_to_exp} days to expiration. "
            if trade.strike_price:
                entry_template += f"Strike: ${trade.strike_price}. "
        if trade.implied_volatility:
            entry_template += f"IV: {trade.implied_volatility:.1f}%. "
    
    if not journal:
        # Create new journal entry with template
        journal = TradingJournal(
            user_id=current_user.id,
            journal_date=trade_date,
            market_outlook=market_template + "Focused on identifying quality setups.",
            daily_goals=f"Execute {setup_description.lower()} with proper risk management.",
            what_went_well="",  # To be filled later
            what_went_wrong="",  # To be filled later  
            lessons_learned="",  # To be filled later
            tomorrow_focus="Review today's trades and prepare for tomorrow's setups.",
            emotional_state="focused",  # Default starting state
            stress_level=3,  # Default moderate level
            discipline_score=8  # Default good discipline
        )
        
        # Add trade-specific notes to daily goals
        if entry_template:
            journal.daily_goals += f"\n\n{entry_template.strip()}"
            
        db.session.add(journal)
        db.session.commit()
        return journal, True  # True indicates new journal created
    else:
        # Update existing journal with additional trade info
        if entry_template and entry_template.strip() not in journal.daily_goals:
            journal.daily_goals += f"\n\n{entry_template.strip()}"
            
        # Update market outlook if it's empty or add to it
        if not journal.market_outlook and market_template:
            journal.market_outlook = market_template + "Focused on identifying quality setups."
        elif market_template and market_template.strip() not in journal.market_outlook:
            journal.market_outlook += f" {market_template.strip()}"
            
        db.session.commit()
        return journal, False  # False indicates existing journal updated

@app.route('/add_trade', methods=['GET', 'POST'])
@login_required
def add_trade():
    form = TradeForm()
    
    if form.validate_on_submit():
        # Handle file uploads
        entry_chart_filename = None
        exit_chart_filename = None
        
        if form.entry_chart_image.data:
            entry_chart_filename = save_uploaded_file(form.entry_chart_image.data, "entry")
        
        if form.exit_chart_image.data:
            exit_chart_filename = save_uploaded_file(form.exit_chart_image.data, "exit")
        
        trade = Trade(
            user_id=current_user.id,
            symbol=form.symbol.data.upper(),
            trade_type=form.trade_type.data,
            entry_date=form.entry_date.data,
            entry_price=form.entry_price.data,
            quantity=form.quantity.data,
            stop_loss=form.stop_loss.data,
            take_profit=form.take_profit.data,
            risk_amount=form.risk_amount.data,
            exit_date=form.exit_date.data,
            exit_price=form.exit_price.data,
            setup_type=form.setup_type.data,
            market_condition=form.market_condition.data,
            timeframe=form.timeframe.data,
            entry_reason=form.entry_reason.data,
            exit_reason=form.exit_reason.data,
            notes=form.notes.data,
            tags=form.tags.data,
            entry_chart_image=entry_chart_filename,
            exit_chart_image=exit_chart_filename,
            # Options-specific fields
            strike_price=form.strike_price.data,
            expiration_date=form.expiration_date.data,
            premium_paid=form.premium_paid.data,
            underlying_price_at_entry=form.underlying_price_at_entry.data,
            underlying_price_at_exit=form.underlying_price_at_exit.data,
            implied_volatility=form.implied_volatility.data,
            delta=form.delta.data,
            gamma=form.gamma.data,
            theta=form.theta.data,
            vega=form.vega.data,
            # Spread-specific fields
            long_strike=form.long_strike.data,
            short_strike=form.short_strike.data,
            long_premium=form.long_premium.data,
            short_premium=form.short_premium.data,
            net_credit=form.net_credit.data
        )
        
        # Set option type from trade type
        if trade.trade_type == 'option_call':
            trade.option_type = 'call'
        elif trade.trade_type == 'option_put':
            trade.option_type = 'put'
        elif trade.trade_type in ['credit_put_spread', 'credit_call_spread']:
            trade.is_spread = True
            trade.spread_type = trade.trade_type
            trade.option_type = 'put' if 'put' in trade.trade_type else 'call'
            # Calculate spread metrics
            trade.calculate_spread_metrics()
        
        # Calculate P&L if trade is closed
        trade.calculate_pnl()
        
        db.session.add(trade)
        db.session.commit()
        
        # Auto-create or update journal entry based on trade
        journal_action = None
        if hasattr(current_user, 'settings') and current_user.settings and current_user.settings.auto_create_journal:
            try:
                journal, is_new = create_or_update_journal_from_trade(trade)
                journal_action = "created" if is_new else "updated"
            except Exception as e:
                print(f"Journal auto-creation failed: {e}")
        
        # Auto-analyze if trade is closed and user has auto-analysis enabled
        if trade.exit_price and hasattr(current_user, 'settings') and current_user.settings.auto_analyze_trades:
            try:
                ai_analyzer.analyze_trade(trade)
                if journal_action:
                    flash(f'Trade added, analyzed, and journal {journal_action} successfully!', 'success')
                else:
                    flash('Trade added and analyzed successfully!', 'success')
            except:
                if journal_action:
                    flash(f'Trade added and journal {journal_action}! Analysis will be done later.', 'success')
                else:
                    flash('Trade added successfully! Analysis will be done later.', 'success')
        else:
            if journal_action:
                flash(f'Trade added and journal {journal_action} successfully!', 'success')
            else:
                flash('Trade added successfully!', 'success')
        
        return redirect(url_for('trades'))
    
    return render_template('add_trade.html', form=form)

@app.route('/trade/<int:id>')
@login_required
def view_trade(id):
    trade = Trade.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    analysis = TradeAnalysis.query.filter_by(trade_id=id).first()
    return render_template('view_trade.html', trade=trade, analysis=analysis)

@app.route('/trade/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_trade(id):
    trade = Trade.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    form = EditTradeForm(obj=trade)
    
    if form.validate_on_submit():
        if form.calculate_pnl.data:
            # Just calculate P&L and return to form
            form.populate_obj(trade)
            trade.calculate_pnl()
            db.session.commit()
            flash('P&L calculated!', 'info')
            return render_template('edit_trade.html', form=form, trade=trade)
        elif form.submit.data:
            # Save the trade
            form.populate_obj(trade)
            trade.calculate_pnl()
            db.session.commit()
            flash('Trade updated successfully!', 'success')
            return redirect(url_for('view_trade', id=trade.id))
    
    return render_template('edit_trade.html', form=form, trade=trade)

@app.route('/trade/<int:id>/analyze', methods=['POST'])
@login_required
def analyze_trade(id):
    trade = Trade.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        analysis = ai_analyzer.analyze_trade(trade)
        if analysis:
            flash('Trade analysis completed!', 'success')
        else:
            flash('Analysis failed. Please check your OpenAI API key.', 'error')
    except Exception as e:
        flash(f'Analysis error: {str(e)}', 'error')
    
    return redirect(url_for('view_trade', id=id))

@app.route('/journal')
@login_required
def journal():
    page = request.args.get('page', 1, type=int)
    journals = TradingJournal.query.filter_by(user_id=current_user.id)\
                                  .order_by(TradingJournal.journal_date.desc())\
                                  .paginate(
                                      page=page, 
                                      per_page=20, 
                                      error_out=False
                                  )
    return render_template('journal.html', journals=journals)

@app.route('/journal/add', methods=['GET', 'POST'])
@app.route('/journal/<journal_date>/edit', methods=['GET', 'POST'])
@login_required
def add_edit_journal(journal_date=None):
    if journal_date:
        # Edit existing journal
        journal_date_obj = datetime.strptime(journal_date, '%Y-%m-%d').date()
        journal = TradingJournal.query.filter_by(
            user_id=current_user.id, 
            journal_date=journal_date_obj
        ).first_or_404()
        form = JournalForm(obj=journal)
        is_edit = True
    else:
        # Add new journal
        journal = None
        form = JournalForm()
        is_edit = False
    
    if form.validate_on_submit():
        if journal:
            # Update existing
            form.populate_obj(journal)
        else:
            # Create new
            journal = TradingJournal(user_id=current_user.id)
            form.populate_obj(journal)
        
        # Get trades for this day and analyze daily performance
        day_trades = journal.get_day_trades()
        if day_trades or journal.daily_pnl:
            try:
                daily_analysis = ai_analyzer.analyze_daily_performance(journal, day_trades)
                if daily_analysis:
                    journal.ai_daily_feedback = daily_analysis['feedback']
                    journal.daily_score = daily_analysis['daily_score']
            except:
                pass  # Continue without AI analysis if it fails
        
        db.session.add(journal)
        db.session.commit()
        
        action = 'updated' if is_edit else 'added'
        flash(f'Journal entry {action} successfully!', 'success')
        return redirect(url_for('journal'))
    
    # Get trades for this day (for context)
    if journal_date:
        day_trades = journal.get_day_trades()
    else:
        day_trades = []
    
    return render_template('add_edit_journal.html', 
                         form=form, 
                         journal=journal, 
                         is_edit=is_edit,
                         day_trades=day_trades)

@app.route('/analytics')
@login_required
def analytics():
    # Get all closed trades for analysis
    closed_trades = Trade.query.filter_by(user_id=current_user.id)\
                              .filter(Trade.exit_price.isnot(None))\
                              .all()
    
    if not closed_trades:
        return render_template('analytics.html', 
                             no_data=True,
                             charts_json=None,
                             stats=None)
    
    # Create analytics data
    df = pd.DataFrame([{
        'date': trade.exit_date,
        'symbol': trade.symbol,
        'pnl': trade.profit_loss or 0,
        'pnl_percent': trade.profit_loss_percent or 0,
        'setup_type': trade.setup_type,
        'timeframe': trade.timeframe,
        'is_winner': trade.is_winner()
    } for trade in closed_trades])
    
    # Calculate statistics
    stats = {
        'total_trades': len(closed_trades),
        'winning_trades': len([t for t in closed_trades if t.is_winner()]),
        'losing_trades': len([t for t in closed_trades if t.profit_loss and t.profit_loss < 0]),
        'win_rate': len([t for t in closed_trades if t.is_winner()]) / len(closed_trades) * 100,
        'total_pnl': sum(t.profit_loss for t in closed_trades if t.profit_loss),
        'avg_win': df[df['pnl'] > 0]['pnl'].mean() if len(df[df['pnl'] > 0]) > 0 else 0,
        'avg_loss': df[df['pnl'] < 0]['pnl'].mean() if len(df[df['pnl'] < 0]) > 0 else 0,
        'largest_win': df['pnl'].max(),
        'largest_loss': df['pnl'].min(),
        'profit_factor': abs(df[df['pnl'] > 0]['pnl'].sum() / df[df['pnl'] < 0]['pnl'].sum()) if df[df['pnl'] < 0]['pnl'].sum() != 0 else 0
    }
    
    # Create charts
    charts = create_analytics_charts(df)
    charts_json = json.dumps(charts, cls=plotly.utils.PlotlyJSONEncoder)
    
    return render_template('analytics.html', 
                         charts_json=charts_json,
                         stats=stats,
                         no_data=False)

def create_analytics_charts(df):
    """Create analytics charts"""
    charts = {}
    
    # P&L over time
    df_sorted = df.sort_values('date')
    df_sorted['cumulative_pnl'] = df_sorted['pnl'].cumsum()
    
    charts['pnl_over_time'] = {
        'data': [{
            'x': df_sorted['date'].tolist(),
            'y': df_sorted['cumulative_pnl'].tolist(),
            'type': 'scatter',
            'mode': 'lines',
            'name': 'Cumulative P&L',
            'line': {'color': '#1f77b4'}
        }],
        'layout': {
            'title': 'Cumulative P&L Over Time',
            'xaxis': {'title': 'Date'},
            'yaxis': {'title': 'Cumulative P&L ($)'},
            'height': 400
        }
    }
    
    # Win/Loss distribution
    win_loss_counts = df['is_winner'].value_counts()
    charts['win_loss_pie'] = {
        'data': [{
            'values': [win_loss_counts.get(True, 0), win_loss_counts.get(False, 0)],
            'labels': ['Wins', 'Losses'],
            'type': 'pie',
            'colors': ['#2ecc71', '#e74c3c']
        }],
        'layout': {
            'title': 'Win/Loss Distribution',
            'height': 400
        }
    }
    
    # Setup type performance
    setup_performance = df.groupby('setup_type')['pnl'].sum().sort_values(ascending=False)
    charts['setup_performance'] = {
        'data': [{
            'x': setup_performance.index.tolist(),
            'y': setup_performance.values.tolist(),
            'type': 'bar',
            'marker': {'color': ['#2ecc71' if x > 0 else '#e74c3c' for x in setup_performance.values]}
        }],
        'layout': {
            'title': 'P&L by Setup Type',
            'xaxis': {'title': 'Setup Type'},
            'yaxis': {'title': 'Total P&L ($)'},
            'height': 400
        }
    }
    
    return charts

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user_settings = current_user.settings
    if not user_settings:
        user_settings = UserSettings(user_id=current_user.id)
        db.session.add(user_settings)
        db.session.commit()
    
    form = UserSettingsForm(obj=user_settings)
    
    if form.validate_on_submit():
        form.populate_obj(user_settings)
        
        # Also update user account size if provided
        if form.account_size.data:
            current_user.account_size = form.account_size.data
        if form.default_risk_percent.data:
            current_user.default_risk_percent = form.default_risk_percent.data
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', form=form)

@app.route('/bulk_analysis', methods=['GET', 'POST'])
@login_required
def bulk_analysis():
    form = BulkAnalysisForm()
    
    if form.validate_on_submit():
        trades_to_analyze = []
        
        if form.analyze_all_unanalyzed.data:
            trades_to_analyze.extend(
                Trade.query.filter_by(user_id=current_user.id, is_analyzed=False)
                          .filter(Trade.exit_price.isnot(None))
                          .all()
            )
        
        if form.analyze_recent.data:
            thirty_days_ago = datetime.now() - timedelta(days=30)
            recent_trades = Trade.query.filter_by(user_id=current_user.id)\
                                     .filter(Trade.entry_date >= thirty_days_ago)\
                                     .filter(Trade.exit_price.isnot(None))\
                                     .all()
            trades_to_analyze.extend(recent_trades)
        
        # Remove duplicates
        trades_to_analyze = list(set(trades_to_analyze))
        
        success_count = 0
        for trade in trades_to_analyze:
            try:
                ai_analyzer.analyze_trade(trade)
                success_count += 1
            except:
                continue
        
        flash(f'Successfully analyzed {success_count} out of {len(trades_to_analyze)} trades.', 'success')
        return redirect(url_for('trades'))
    
    # Get counts for display
    unanalyzed_count = Trade.query.filter_by(user_id=current_user.id, is_analyzed=False)\
                                 .filter(Trade.exit_price.isnot(None))\
                                 .count()
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_count = Trade.query.filter_by(user_id=current_user.id)\
                             .filter(Trade.entry_date >= thirty_days_ago)\
                             .filter(Trade.exit_price.isnot(None))\
                             .count()
    
    return render_template('bulk_analysis.html', 
                         form=form,
                         unanalyzed_count=unanalyzed_count,
                         recent_count=recent_count)

@app.route('/api/quick_trade', methods=['POST'])
@login_required
def api_quick_trade():
    """API endpoint for quick trade entry"""
    form = QuickTradeForm()
    
    if form.validate_on_submit():
        trade = Trade(
            user_id=current_user.id,
            symbol=form.symbol.data.upper(),
            trade_type=form.trade_type.data,
            entry_date=datetime.now(),
            entry_price=form.entry_price.data,
            quantity=form.quantity.data,
            setup_type=form.setup_type.data,
            timeframe='day_trade'  # Default for quick trades
        )
        
        db.session.add(trade)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Trade added successfully!',
            'trade_id': trade.id
        })
    
    return jsonify({
        'success': False,
        'errors': form.errors
    })

@app.route('/tools')
@login_required
def tools():
    """Tools and calculators main page"""
    return render_template('tools/index.html')

@app.route('/tools/options-calculator', methods=['GET', 'POST'])
def options_calculator():
    """Options calculator with live data and Black-Scholes pricing"""
    context = {
        'symbol': None,
        'current_price': None,
        'options_data': None,
        'expiration_dates': None,
        'selected_date': None,
        'stock_name': None,
        'combined_options': []
    }
    
    if request.method == 'POST':
        symbol = request.form.get('symbol', '').upper()
        context['symbol'] = symbol
        
        if symbol:
            try:
                # Try to get stock info and current price
                # First try Tradier API
                current_price = get_stock_price_tradier(symbol)
                stock_name = symbol  # Default to symbol
                
                # If Tradier fails, fallback to yfinance for stock info
                if not current_price:
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info
                        stock_name = info.get('longName', symbol)
                        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                    except:
                        stock_name = symbol
                        current_price = 0
                
                context['stock_name'] = stock_name
                context['current_price'] = current_price
                
                # Get expiration dates - try Tradier first
                expiration_dates = []
                try:
                    headers = get_tradier_headers()
                    if headers:  # Only try Tradier if token is configured
                        exp_url = f"{TRADIER_API_BASE}/markets/options/expirations"
                        exp_params = {'symbol': symbol}
                        
                        exp_response = requests.get(exp_url, params=exp_params, headers=headers)
                        if exp_response.status_code == 200:
                            exp_data = exp_response.json()
                            if 'expirations' in exp_data and exp_data['expirations']:
                                dates = exp_data['expirations']['date']
                                if isinstance(dates, str):
                                    expiration_dates = [dates]
                                else:
                                    expiration_dates = list(dates)
                except Exception as e:
                    print(f"Tradier API error for expirations: {e}")
                    pass
                
                # Fallback to yfinance for expiration dates if Tradier fails
                if not expiration_dates:
                    try:
                        ticker = yf.Ticker(symbol)
                        exp_dates = ticker.options
                        expiration_dates = list(exp_dates) if exp_dates else []
                    except Exception as e:
                        print(f"YFinance error for expirations: {e}")
                        expiration_dates = []
                
                context['expiration_dates'] = expiration_dates
                
                # If expiration date is selected, get options chain
                expiration_date = request.form.get('expiration_date')
                if expiration_date and expiration_date in expiration_dates:
                    context['selected_date'] = expiration_date
                    calls, puts, chain_current_price = get_options_chain(symbol, expiration_date)
                    
                    if calls is not None and puts is not None:
                        # Use the price from options chain if available
                        if chain_current_price:
                            context['current_price'] = chain_current_price
                        
                        # Combine calls and puts by strike price
                        combined_options = []
                        
                        # Handle both DataFrame (yfinance) and list (potential other sources)
                        if hasattr(calls, 'empty') and not calls.empty:
                            call_strikes = set(calls['strike'].tolist())
                        else:
                            call_strikes = set()
                            
                        if hasattr(puts, 'empty') and not puts.empty:
                            put_strikes = set(puts['strike'].tolist())
                        else:
                            put_strikes = set()
                        
                        all_strikes = sorted(call_strikes.union(put_strikes))
                        
                        for strike in all_strikes:
                            # Handle call data
                            if hasattr(calls, 'empty') and not calls.empty:
                                call_data = calls[calls['strike'] == strike]
                                if not call_data.empty:
                                    call_row = call_data.iloc[0]
                                    call_option = {
                                        'strike': strike,
                                        'last': call_row.get('last', 0),
                                        'bid': call_row.get('bid', 0),
                                        'ask': call_row.get('ask', 0),
                                        'volume': call_row.get('volume', 0),
                                        'open_interest': call_row.get('open_interest', call_row.get('openInterest', 0)),
                                        'implied_volatility': call_row.get('implied_volatility', call_row.get('impliedVolatility', 0))
                                    }
                                else:
                                    call_option = {
                                        'strike': strike, 'last': 0, 'bid': 0, 'ask': 0, 
                                        'volume': 0, 'open_interest': 0, 'implied_volatility': 0
                                    }
                            else:
                                call_option = {
                                    'strike': strike, 'last': 0, 'bid': 0, 'ask': 0, 
                                    'volume': 0, 'open_interest': 0, 'implied_volatility': 0
                                }
                            
                            # Handle put data
                            if hasattr(puts, 'empty') and not puts.empty:
                                put_data = puts[puts['strike'] == strike]
                                if not put_data.empty:
                                    put_row = put_data.iloc[0]
                                    put_option = {
                                        'strike': strike,
                                        'last': put_row.get('last', 0),
                                        'bid': put_row.get('bid', 0),
                                        'ask': put_row.get('ask', 0),
                                        'volume': put_row.get('volume', 0),
                                        'open_interest': put_row.get('open_interest', put_row.get('openInterest', 0)),
                                        'implied_volatility': put_row.get('implied_volatility', put_row.get('impliedVolatility', 0))
                                    }
                                else:
                                    put_option = {
                                        'strike': strike, 'last': 0, 'bid': 0, 'ask': 0, 
                                        'volume': 0, 'open_interest': 0, 'implied_volatility': 0
                                    }
                            else:
                                put_option = {
                                    'strike': strike, 'last': 0, 'bid': 0, 'ask': 0, 
                                    'volume': 0, 'open_interest': 0, 'implied_volatility': 0
                                }
                            
                            combined_options.append((call_option, put_option))
                        
                        context['combined_options'] = combined_options
                    else:
                        context['combined_options'] = []
                
            except Exception as e:
                print(f"Options calculator error: {e}")
                flash(f'Error fetching options data: {str(e)}', 'danger')
    
    return render_template('tools/options_calculator.html', context=context)

@app.route('/tools/options-pnl', methods=['POST'])
def calculate_options_pnl():
    """Scenario analysis for options P&L, matching stockappvscode logic and output structure."""
    try:
        import numpy as np
        from datetime import datetime
        print('--- OPTIONS PNL DEBUG START ---')
        data = request.get_json()
        print('Input data:', data)
        option_type = data.get('option_type')
        strike_price = float(data.get('strike'))
        current_price = float(data.get('current_price'))
        expiration_date = data.get('expiration_date')
        premium = float(data.get('premium'))
        quantity = int(data.get('quantity', 1))
        print(f'Parsed: option_type={option_type}, strike_price={strike_price}, current_price={current_price}, expiration_date={expiration_date}, premium={premium}, quantity={quantity}')

        # Calculate days until expiration
        exp_date = datetime.strptime(expiration_date, '%Y-%m-%d')
        days_to_exp = (exp_date - datetime.now()).days
        print(f'days_to_exp: {days_to_exp}')

        # Generate price range (±15% from current price, 11 points)
        price_range = np.linspace(current_price * 0.85, current_price * 1.15, 11)
        print('price_range:', price_range)

        # Generate realistic time points
        time_points = []
        if days_to_exp <= 0:
            time_points = [0]
        elif days_to_exp <= 7:
            time_points = list(range(days_to_exp, -1, -1))[:5]
        elif days_to_exp <= 30:
            intervals = [days_to_exp, max(0, days_to_exp - 7), max(0, days_to_exp - 14), max(0, days_to_exp - 21), 0]
            time_points = sorted(list(set([d for d in intervals if d >= 0])), reverse=True)
        elif days_to_exp <= 90:
            intervals = [days_to_exp, max(0, days_to_exp - 14), max(0, days_to_exp - 30), max(0, days_to_exp - 60), 0]
            time_points = sorted(list(set([d for d in intervals if d >= 0])), reverse=True)
        else:
            intervals = [days_to_exp, max(0, days_to_exp - 30), max(0, days_to_exp - 60), max(0, days_to_exp - 90), 0]
            time_points = sorted(list(set([d for d in intervals if d >= 0])), reverse=True)
        if 0 not in time_points:
            time_points.append(0)
            time_points.sort(reverse=True)
        print('time_points:', time_points)

        # Calculate implied volatility from current premium (Newton-Raphson)
        def black_scholes(S, K, T, r, sigma, option_type='call'):
            r = 0.05
            d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
            d2 = d1 - sigma*np.sqrt(T)
            if option_type == 'call':
                price = S*np.exp(-0*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
            else:
                price = K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-0*T)*norm.cdf(-d1)
            return price
        def calculate_implied_volatility(market_price, S, K, T, r, option_type):
            if T <= 0:
                return 0.3
            volatility = 0.3
            for _ in range(10):
                try:
                    theoretical_price = black_scholes(S, K, T, r, volatility, option_type)
                    d1 = (np.log(S/K) + (r + volatility**2/2)*T) / (volatility*np.sqrt(T))
                    vega = S * norm.pdf(d1) * np.sqrt(T)
                    if abs(vega) < 1e-6:
                        break
                    price_diff = theoretical_price - market_price
                    if abs(price_diff) < 0.01:
                        break
                    volatility = volatility - price_diff / vega
                    volatility = max(0.05, min(2.0, volatility))
                except Exception as e:
                    print('IV calc error:', e)
                    break
            return volatility
        years_to_exp = days_to_exp / 365.0
        print('years_to_exp:', years_to_exp)
        if years_to_exp > 0 and premium > 0:
            implied_vol = calculate_implied_volatility(premium, current_price, strike_price, years_to_exp, 0.05, option_type)
        else:
            implied_vol = 0.3
        print('implied_vol:', implied_vol)

        pnl_data = []
        contract_multiplier = 100
        for price in price_range:
            time_data = []
            for days_left in time_points:
                years_left = days_left / 365.0
                if years_left > 0:
                    theoretical_price = black_scholes(price, strike_price, years_left, 0.05, implied_vol, option_type)
                else:
                    if option_type == 'call':
                        theoretical_price = max(0, price - strike_price)
                    else:
                        theoretical_price = max(0, strike_price - price)
                pnl = (theoretical_price - premium) * contract_multiplier
                return_percent = (pnl / (premium * contract_multiplier)) * 100 if premium > 0 else 0
                time_data.append({
                    'days_remaining': days_left,
                    'pnl': round(pnl, 2),
                    'return_percent': round(return_percent, 2)
                })
            pnl_data.append({
                'stock_price': round(price, 2),
                'time_data': time_data
            })
        response_data = {
            'pnl_data': pnl_data,
            'option_info': {
                'type': option_type,
                'strike': strike_price,
                'premium': premium,
                'days_to_expiration': days_to_exp,
                'time_points': time_points,
                'implied_volatility': round(implied_vol * 100, 1),
                'current_stock_price': current_price
            }
        }
        print('--- OPTIONS PNL DEBUG END ---')
        return jsonify({'success': True, 'analysis': response_data})
    except Exception as e:
        import traceback
        print(f"Options P&L calculation error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/tools/black-scholes')
@login_required
def black_scholes_calculator():
    """Black-Scholes options pricing calculator"""
    return render_template('tools/black_scholes.html')

@app.route('/tools/calculate-bs', methods=['POST'])
@login_required
def calculate_black_scholes():
    """Calculate Black-Scholes price and Greeks"""
    try:
        data = request.get_json()
        
        S = float(data.get('stock_price'))
        K = float(data.get('strike_price'))
        T = float(data.get('time_to_expiration')) / 365.0
        r = float(data.get('risk_free_rate')) / 100.0
        sigma = float(data.get('volatility')) / 100.0
        option_type = data.get('option_type')
        
        # Calculate price
        price = black_scholes(S, K, T, r, sigma, option_type)
        
        # Calculate Greeks
        greeks = calculate_greeks(S, K, T, r, sigma, option_type)
        
        return jsonify({
            'success': True,
            'price': round(price, 4),
            'greeks': greeks
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/tools/stock-lookup')
@login_required
def stock_lookup():
    """Stock information lookup tool"""
    return render_template('tools/stock_lookup.html')

@app.route('/api/stock-info/<symbol>')
@login_required
def get_stock_info(symbol):
    """Get stock information via API"""
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        hist = ticker.history(period="1mo")
        
        result = {
            'success': True,
            'data': {
                'symbol': symbol.upper(),
                'name': info.get('longName', 'N/A'),
                'current_price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                'previous_close': info.get('previousClose', 0),
                'change': info.get('regularMarketChange', 0),
                'change_percent': info.get('regularMarketChangePercent', 0),
                'volume': info.get('volume', 0),
                'market_cap': info.get('marketCap', 0),
                'pe_ratio': info.get('trailingPE', 0),
                'dividend_yield': info.get('dividendYield', 0),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh', 0),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow', 0),
                'chart_data': {
                    'dates': [d.strftime('%Y-%m-%d') for d in hist.index],
                    'prices': hist['Close'].tolist()
                }
            }
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/search_stocks')
@login_required
def search_stocks():
    """Search for stock symbols and company names - comprehensive options-enabled stocks"""
    query = request.args.get('q', '').strip().upper()
    
    if len(query) < 1:
        return jsonify([])
    
    # Comprehensive list of stocks with active options trading
    stocks_with_options = [
        # Major Tech Stocks
        {'symbol': 'AAPL', 'name': 'Apple Inc.'},
        {'symbol': 'GOOGL', 'name': 'Alphabet Inc. Class A'},
        {'symbol': 'GOOG', 'name': 'Alphabet Inc. Class C'},
        {'symbol': 'MSFT', 'name': 'Microsoft Corporation'},
        {'symbol': 'AMZN', 'name': 'Amazon.com Inc.'},
        {'symbol': 'TSLA', 'name': 'Tesla Inc.'},
        {'symbol': 'META', 'name': 'Meta Platforms Inc.'},
        {'symbol': 'NVDA', 'name': 'NVIDIA Corporation'},
        {'symbol': 'NFLX', 'name': 'Netflix Inc.'},
        {'symbol': 'AMD', 'name': 'Advanced Micro Devices Inc.'},
        {'symbol': 'INTC', 'name': 'Intel Corporation'},
        {'symbol': 'ORCL', 'name': 'Oracle Corporation'},
        {'symbol': 'CRM', 'name': 'Salesforce Inc.'},
        {'symbol': 'ADBE', 'name': 'Adobe Inc.'},
        {'symbol': 'IBM', 'name': 'International Business Machines Corporation'},
        {'symbol': 'CSCO', 'name': 'Cisco Systems Inc.'},
        {'symbol': 'AVGO', 'name': 'Broadcom Inc.'},
        {'symbol': 'TXN', 'name': 'Texas Instruments Incorporated'},
        {'symbol': 'QCOM', 'name': 'QUALCOMM Incorporated'},
        {'symbol': 'MU', 'name': 'Micron Technology Inc.'},
        
        # Financial Sector
        {'symbol': 'JPM', 'name': 'JPMorgan Chase & Co.'},
        {'symbol': 'BAC', 'name': 'Bank of America Corporation'},
        {'symbol': 'WFC', 'name': 'Wells Fargo & Company'},
        {'symbol': 'GS', 'name': 'The Goldman Sachs Group Inc.'},
        {'symbol': 'MS', 'name': 'Morgan Stanley'},
        {'symbol': 'C', 'name': 'Citigroup Inc.'},
        {'symbol': 'AXP', 'name': 'American Express Company'},
        {'symbol': 'V', 'name': 'Visa Inc.'},
        {'symbol': 'MA', 'name': 'Mastercard Incorporated'},
        {'symbol': 'PYPL', 'name': 'PayPal Holdings Inc.'},
        {'symbol': 'SQ', 'name': 'Block Inc.'},
        {'symbol': 'BRK.B', 'name': 'Berkshire Hathaway Inc. Class B'},
        
        # Consumer & Retail
        {'symbol': 'WMT', 'name': 'Walmart Inc.'},
        {'symbol': 'HD', 'name': 'The Home Depot Inc.'},
        {'symbol': 'COST', 'name': 'Costco Wholesale Corporation'},
        {'symbol': 'TGT', 'name': 'Target Corporation'},
        {'symbol': 'LOW', 'name': 'Lowe\'s Companies Inc.'},
        {'symbol': 'NKE', 'name': 'NIKE Inc.'},
        {'symbol': 'SBUX', 'name': 'Starbucks Corporation'},
        {'symbol': 'MCD', 'name': 'McDonald\'s Corporation'},
        {'symbol': 'DIS', 'name': 'The Walt Disney Company'},
        {'symbol': 'AMGN', 'name': 'Amgen Inc.'},
        
        # Healthcare & Pharma
        {'symbol': 'JNJ', 'name': 'Johnson & Johnson'},
        {'symbol': 'PFE', 'name': 'Pfizer Inc.'},
        {'symbol': 'UNH', 'name': 'UnitedHealth Group Incorporated'},
        {'symbol': 'ABBV', 'name': 'AbbVie Inc.'},
        {'symbol': 'TMO', 'name': 'Thermo Fisher Scientific Inc.'},
        {'symbol': 'ABT', 'name': 'Abbott Laboratories'},
        {'symbol': 'LLY', 'name': 'Eli Lilly and Company'},
        {'symbol': 'BMY', 'name': 'Bristol-Myers Squibb Company'},
        {'symbol': 'MRK', 'name': 'Merck & Co. Inc.'},
        {'symbol': 'GILD', 'name': 'Gilead Sciences Inc.'},
        
        # Energy & Commodities
        {'symbol': 'XOM', 'name': 'Exxon Mobil Corporation'},
        {'symbol': 'CVX', 'name': 'Chevron Corporation'},
        {'symbol': 'COP', 'name': 'ConocoPhillips'},
        {'symbol': 'SLB', 'name': 'Schlumberger Limited'},
        {'symbol': 'EOG', 'name': 'EOG Resources Inc.'},
        
        # Popular ETFs with Options
        {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF Trust'},
        {'symbol': 'QQQ', 'name': 'Invesco QQQ Trust'},
        {'symbol': 'IWM', 'name': 'iShares Russell 2000 ETF'},
        {'symbol': 'DIA', 'name': 'SPDR Dow Jones Industrial Average ETF'},
        {'symbol': 'VOO', 'name': 'Vanguard S&P 500 ETF'},
        {'symbol': 'VTI', 'name': 'Vanguard Total Stock Market ETF'},
        {'symbol': 'EEM', 'name': 'iShares MSCI Emerging Markets ETF'},
        {'symbol': 'GLD', 'name': 'SPDR Gold Shares'},
        {'symbol': 'SLV', 'name': 'iShares Silver Trust'},
        {'symbol': 'TLT', 'name': 'iShares 20+ Year Treasury Bond ETF'},
        {'symbol': 'ARKK', 'name': 'ARK Innovation ETF'},
        {'symbol': 'XLF', 'name': 'Financial Select Sector SPDR Fund'},
        {'symbol': 'XLE', 'name': 'Energy Select Sector SPDR Fund'},
        {'symbol': 'XLK', 'name': 'Technology Select Sector SPDR Fund'},
        {'symbol': 'XLI', 'name': 'Industrial Select Sector SPDR Fund'},
        {'symbol': 'XLV', 'name': 'Health Care Select Sector SPDR Fund'},
        {'symbol': 'XLP', 'name': 'Consumer Staples Select Sector SPDR Fund'},
        
        # Meme Stocks & Popular Trading Names
        {'symbol': 'GME', 'name': 'GameStop Corp.'},
        {'symbol': 'AMC', 'name': 'AMC Entertainment Holdings Inc.'},
        {'symbol': 'BB', 'name': 'BlackBerry Limited'},
        {'symbol': 'BBBY', 'name': 'Bed Bath & Beyond Inc.'},
        {'symbol': 'NOK', 'name': 'Nokia Corporation'},
        {'symbol': 'PLTR', 'name': 'Palantir Technologies Inc.'},
        {'symbol': 'SOFI', 'name': 'SoFi Technologies Inc.'},
        
        # Transportation & Travel
        {'symbol': 'UBER', 'name': 'Uber Technologies Inc.'},
        {'symbol': 'LYFT', 'name': 'Lyft Inc.'},
        {'symbol': 'AAL', 'name': 'American Airlines Group Inc.'},
        {'symbol': 'DAL', 'name': 'Delta Air Lines Inc.'},
        {'symbol': 'UAL', 'name': 'United Airlines Holdings Inc.'},
        {'symbol': 'CCL', 'name': 'Carnival Corporation & plc'},
        {'symbol': 'NCLH', 'name': 'Norwegian Cruise Line Holdings Ltd.'},
        
        # Communication & Media
        {'symbol': 'T', 'name': 'AT&T Inc.'},
        {'symbol': 'VZ', 'name': 'Verizon Communications Inc.'},
        {'symbol': 'CMCSA', 'name': 'Comcast Corporation'},
        {'symbol': 'SNAP', 'name': 'Snap Inc.'},
        {'symbol': 'TWTR', 'name': 'Twitter Inc.'},
        {'symbol': 'PINS', 'name': 'Pinterest Inc.'},
        
        # Industrial & Manufacturing
        {'symbol': 'BA', 'name': 'The Boeing Company'},
        {'symbol': 'CAT', 'name': 'Caterpillar Inc.'},
        {'symbol': 'GE', 'name': 'General Electric Company'},
        {'symbol': 'MMM', 'name': '3M Company'},
        {'symbol': 'F', 'name': 'Ford Motor Company'},
        {'symbol': 'GM', 'name': 'General Motors Company'},
        
        # Consumer Goods
        {'symbol': 'PG', 'name': 'Procter & Gamble Company'},
        {'symbol': 'KO', 'name': 'The Coca-Cola Company'},
        {'symbol': 'PEP', 'name': 'PepsiCo Inc.'},
        {'symbol': 'CL', 'name': 'Colgate-Palmolive Company'},
        {'symbol': 'KMB', 'name': 'Kimberly-Clark Corporation'},
        
        # Real Estate & REITs
        {'symbol': 'SPG', 'name': 'Simon Property Group Inc.'},
        {'symbol': 'AMT', 'name': 'American Tower Corporation'},
        {'symbol': 'PLD', 'name': 'Prologis Inc.'},
        {'symbol': 'CCI', 'name': 'Crown Castle International Corp.'},
        
        # Chinese ADRs with Options
        {'symbol': 'BABA', 'name': 'Alibaba Group Holding Limited'},
        {'symbol': 'JD', 'name': 'JD.com Inc.'},
        {'symbol': 'PDD', 'name': 'PDD Holdings Inc.'},
        {'symbol': 'BIDU', 'name': 'Baidu Inc.'},
        {'symbol': 'NIO', 'name': 'NIO Inc.'},
        {'symbol': 'XPEV', 'name': 'XPeng Inc.'},
        {'symbol': 'LI', 'name': 'Li Auto Inc.'},
        
        # Biotech & Innovation
        {'symbol': 'BIIB', 'name': 'Biogen Inc.'},
        {'symbol': 'REGN', 'name': 'Regeneron Pharmaceuticals Inc.'},
        {'symbol': 'MRNA', 'name': 'Moderna Inc.'},
        {'symbol': 'BNTX', 'name': 'BioNTech SE'},
        {'symbol': 'ZM', 'name': 'Zoom Video Communications Inc.'},
        {'symbol': 'PTON', 'name': 'Peloton Interactive Inc.'},
        {'symbol': 'ROKU', 'name': 'Roku Inc.'},
        {'symbol': 'DOCU', 'name': 'DocuSign Inc.'},
        
        # Cannabis & Growth
        {'symbol': 'TLRY', 'name': 'Tilray Brands Inc.'},
        {'symbol': 'CGC', 'name': 'Canopy Growth Corporation'},
        {'symbol': 'ACB', 'name': 'Aurora Cannabis Inc.'},
        
        # E-commerce & Digital
        {'symbol': 'SHOP', 'name': 'Shopify Inc.'},
        {'symbol': 'ETSY', 'name': 'Etsy Inc.'},
        {'symbol': 'EBAY', 'name': 'eBay Inc.'},
        {'symbol': 'TWLO', 'name': 'Twilio Inc.'},
        {'symbol': 'OKTA', 'name': 'Okta Inc.'},
        {'symbol': 'SNOW', 'name': 'Snowflake Inc.'},
        {'symbol': 'CRWD', 'name': 'CrowdStrike Holdings Inc.'},
        
        # Commodity & Mining
        {'symbol': 'GOLD', 'name': 'Barrick Gold Corporation'},
        {'symbol': 'NEM', 'name': 'Newmont Corporation'},
        {'symbol': 'FCX', 'name': 'Freeport-McMoRan Inc.'},
        
        # Utilities
        {'symbol': 'NEE', 'name': 'NextEra Energy Inc.'},
        {'symbol': 'DUK', 'name': 'Duke Energy Corporation'},
        {'symbol': 'SO', 'name': 'The Southern Company'},
        
        # Semiconductor
        {'symbol': 'TSM', 'name': 'Taiwan Semiconductor Manufacturing Company Limited'},
        {'symbol': 'ASML', 'name': 'ASML Holding N.V.'},
        {'symbol': 'LRCX', 'name': 'Lam Research Corporation'},
        {'symbol': 'AMAT', 'name': 'Applied Materials Inc.'},
        {'symbol': 'KLAC', 'name': 'KLA Corporation'},
        
        # Volatile/High IV Stocks
        {'symbol': 'SPCE', 'name': 'Virgin Galactic Holdings Inc.'},
        {'symbol': 'HOOD', 'name': 'Robinhood Markets Inc.'},
        {'symbol': 'COIN', 'name': 'Coinbase Global Inc.'},
        {'symbol': 'RIVN', 'name': 'Rivian Automotive Inc.'},
        {'symbol': 'LCID', 'name': 'Lucid Group Inc.'},
        
        # Financial Technology
        {'symbol': 'AFRM', 'name': 'Affirm Holdings Inc.'},
        {'symbol': 'UPST', 'name': 'Upstart Holdings Inc.'},
        {'symbol': 'LMND', 'name': 'Lemonade Inc.'},
        
        # Inverse/VIX ETFs (for hedging)
        {'symbol': 'VIX', 'name': 'CBOE Volatility Index'},
        {'symbol': 'UVXY', 'name': 'ProShares Ultra VIX Short-Term Futures ETF'},
        {'symbol': 'SQQQ', 'name': 'ProShares UltraPro Short QQQ'},
        {'symbol': 'SPXS', 'name': 'Direxion Daily S&P 500 Bear 3X Shares'},
        {'symbol': 'TQQQ', 'name': 'ProShares UltraPro QQQ'},
        {'symbol': 'SPXL', 'name': 'Direxion Daily S&P 500 Bull 3X Shares'},
    ]
    
    # Filter stocks based on query - search both symbol and name
    matches = []
    for stock in stocks_with_options:
        symbol_match = query in stock['symbol']
        name_match = query in stock['name'].upper()
        
        if symbol_match or name_match:
            # Boost exact symbol matches to top
            if stock['symbol'] == query:
                matches.insert(0, stock)
            elif stock['symbol'].startswith(query):
                matches.insert(min(3, len(matches)), stock)
            else:
                matches.append(stock)
        
        if len(matches) >= 15:  # Increased to 15 results for better search
            break
    
    return jsonify(matches)

@app.route('/test-tradier/<symbol>')
@login_required
def test_tradier_api(symbol):
    """Test endpoint to debug Tradier API connection"""
    symbol = symbol.upper()
    print(f"Testing Tradier API for {symbol}")
    
    result = {
        'symbol': symbol,
        'tradier_configured': TRADIER_TOKEN != 'your_tradier_token_here' and TRADIER_TOKEN,
        'api_endpoint': TRADIER_API_BASE,
        'token_length': len(TRADIER_TOKEN) if TRADIER_TOKEN else 0,
        'stock_price_test': None,
        'expirations_test': None,
        'options_chain_test': None,
        'errors': []
    }
    
    # Test 1: Stock price
    try:
        price = get_stock_price_tradier(symbol)
        result['stock_price_test'] = {
            'success': price is not None,
            'price': price
        }
    except Exception as e:
        result['errors'].append(f"Stock price error: {str(e)}")
    
    # Test 2: Get expirations
    try:
        headers = get_tradier_headers()
        if headers:
            exp_url = f"{TRADIER_API_BASE}/markets/options/expirations"
            exp_params = {'symbol': symbol}
            exp_response = requests.get(exp_url, params=exp_params, headers=headers)
            
            result['expirations_test'] = {
                'status_code': exp_response.status_code,
                'success': exp_response.status_code == 200,
                'response_preview': exp_response.text[:200] if exp_response.text else 'Empty'
            }
            
            if exp_response.status_code == 200:
                exp_data = exp_response.json()
                if 'expirations' in exp_data and exp_data['expirations']:
                    expirations = exp_data['expirations']['date']
                    if isinstance(expirations, str):
                        expirations = [expirations]
                    result['expirations_test']['expiration_count'] = len(expirations)
                    result['expirations_test']['first_few'] = expirations[:3]
        else:
            result['errors'].append("No valid headers for Tradier API")
    except Exception as e:
        result['errors'].append(f"Expirations error: {str(e)}")
    
    # Test 3: Full options chain
    try:
        calls, puts, price, expirations = get_options_chain_tradier(symbol)
        result['options_chain_test'] = {
            'success': calls is not None and puts is not None,
            'calls_count': len(calls) if calls is not None else 0,
            'puts_count': len(puts) if puts is not None else 0,
            'current_price': price,
            'expiration_count': len(expirations) if expirations else 0
        }
    except Exception as e:
        result['errors'].append(f"Options chain error: {str(e)}")
    
    return jsonify(result)

@app.route('/test-options/<symbol>')
@login_required
def test_options(symbol):
    """Test endpoint to debug options chain issues (redirect to Tradier test)"""
    return redirect(url_for('test_tradier_api', symbol=symbol))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.route('/api/refresh-pnl', methods=['POST'])
@login_required
def refresh_pnl():
    """API endpoint to refresh P&L for all open positions"""
    try:
        update_open_positions_pnl(current_user.id)
        
        # Get updated open trades count and total unrealized P&L
        open_trades = Trade.query.filter_by(user_id=current_user.id)\
                                .filter(Trade.exit_price.is_(None))\
                                .all()
        
        total_unrealized = sum(trade.profit_loss for trade in open_trades if trade.profit_loss)
        
        return jsonify({
            'success': True,
            'message': f'Updated P&L for {len(open_trades)} open position(s)',
            'open_positions': len(open_trades),
            'total_unrealized_pnl': round(total_unrealized, 2)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

def calculate_option_pnl(option_type, strike_price, premium, price):
    """Calculate P&L for a single price point"""
    contract_multiplier = 100
    
    # Calculate P&L
    if option_type == 'call':
        if price <= strike_price:
            pnl = -premium * contract_multiplier  # Out of the money - lose premium
        else:
            pnl = ((price - strike_price) - premium) * contract_multiplier  # In the money - profit minus premium
    else:  # put
        if price >= strike_price:
            pnl = -premium * contract_multiplier  # Out of the money - lose premium
        else:
            pnl = ((strike_price - price) - premium) * contract_multiplier  # In the money - profit minus premium
    
    # Calculate ROI
    roi = (pnl / (premium * contract_multiplier)) * 100 if premium > 0 else 0
    
    return {
        'price': float(price),
        'pnl': float(pnl),
        'roi': float(roi)
    }

if __name__ == '__main__':
    app.run(debug=True) 