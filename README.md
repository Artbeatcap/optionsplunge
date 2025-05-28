# Options Plunge - AI Trading Analysis Platform

A comprehensive Flask-based web application for tracking, analyzing, and improving your options trading performance using AI-powered insights.

## Features

- **Options Calculator**: Real-time options chains with P&L analysis, Greeks calculation, and comprehensive profit/loss scenarios
- **Trade Tracking**: Log stock and options trades with detailed entry/exit information
- **AI Analysis**: Get AI-powered insights on your trades to improve performance
- **Trading Tools**: Black-Scholes calculator and options chain lookup with live market data
- **Trading Journal**: Daily journal entries to track market conditions and emotional state
- **Analytics Dashboard**: Comprehensive performance analytics and charts
- **Stock Lookup**: Real-time stock price and information lookup
- **Chart Upload**: Upload entry/exit charts for better trade analysis

## Quick Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-change-this-in-production
DEBUG=True
FLASK_ENV=development

# Database Configuration
DATABASE_URL=sqlite:///trading_app.db

# API Keys (Optional - for enhanced features)
OPENAI_API_KEY=your-openai-api-key-here
TRADIER_API_TOKEN=your-tradier-token-here

# Email Configuration (Optional - for notifications)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-email-password
```

### 3. Initialize and Run the Application

```bash
python app.py
```

This will:
- Create the database and all necessary tables
- Create a default admin user (username: `admin`, password: `admin123`)
- Start the application on `http://localhost:5000`

### 4. First Login

1. Navigate to `http://localhost:5000`
2. Click "Login" and use:
   - Username: `admin`
   - Password: `admin123`
3. **Important**: Change the admin password immediately after first login!

## Application Structure

```
trading-app-clean/
├── app.py                 # Main application entry point
├── app_original.py        # Core Flask routes and logic
├── config.py             # Configuration settings
├── models.py             # Database models
├── forms.py              # Flask-WTF forms
├── ai_analysis.py        # AI analysis functionality
├── requirements.txt      # Python dependencies
├── static/
│   └── uploads/          # Uploaded chart images
└── templates/
    ├── *.html            # Main HTML templates
    └── tools/            # Trading tools templates
```

## Key Models

- **User**: User accounts and preferences
- **Trade**: Individual trade records (stocks and options)
- **TradeAnalysis**: AI-generated trade analysis
- **TradingJournal**: Daily journal entries
- **UserSettings**: User preferences and settings

## Trading Tools

### Options Calculator
- Calculate potential P&L for options strategies
- Support for single options and spreads
- Real-time options chain data (requires API key)

### Black-Scholes Calculator
- Calculate theoretical option prices
- Greeks calculation (Delta, Gamma, Theta, Vega)
- Implied volatility analysis

### Stock Lookup
- Real-time stock quotes
- Company information
- Historical data

## API Integration

### Tradier API (Optional)
For real-time options data and stock quotes:
1. Sign up at [Tradier](https://tradier.com/)
2. Get your API token
3. Add it to your `.env` file as `TRADIER_API_TOKEN`

### OpenAI API (Optional)
For AI-powered trade analysis:
1. Get an API key from [OpenAI](https://openai.com/)
2. Add it to your `.env` file as `OPENAI_API_KEY`

## Database

The application uses SQLite by default, which is perfect for single-user setups. The database file (`trading_app.db`) will be created automatically when you run the app.

For production or multi-user setups, you can configure PostgreSQL or MySQL by changing the `DATABASE_URL` in your `.env` file.

## Development

### Running in Development Mode

```bash
# Set environment
export FLASK_ENV=development
export FLASK_APP=app.py

# Run with Flask development server
flask run
```

### Database Management

The app automatically creates tables on first run. If you need to reset the database:

```bash
rm trading_app.db  # Delete existing database
python app.py      # Restart to recreate tables
```

## Security Notes

1. **Change the default admin password** immediately after first login
2. **Use a strong SECRET_KEY** in production
3. **Never commit your `.env` file** to version control
4. **Use environment variables** for all sensitive data in production

## Troubleshooting

### Common Issues

1. **Import Errors**: Make sure all dependencies are installed with `pip install -r requirements.txt`
2. **Database Errors**: Delete the database file and restart the app to recreate tables
3. **Port Already in Use**: Change the port in `app.py` or stop other Flask applications

### Getting Help

If you encounter issues:
1. Check the console output for error messages
2. Ensure all required dependencies are installed
3. Verify your `.env` file configuration
4. Check that the `static/uploads` directory exists and is writable

## License

This project is for personal use. Please ensure compliance with any third-party API terms of service when using external data providers. 