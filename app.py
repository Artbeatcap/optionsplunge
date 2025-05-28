#!/usr/bin/env python3
"""
AI Trading Analysis Application
Main application entry point
"""

import os
from flask import Flask
from models import db, User, Trade, TradeAnalysis, TradingJournal, UserSettings
from config import Config

def create_app(config_class=Config):
    """Create and configure the Flask application"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize upload folder
    Config.init_app(app)
    
    return app

def init_database(app):
    """Initialize the database with tables"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database tables created successfully!")
        
        # Check if admin user exists, create if not
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@example.com'
            )
            admin_user.set_password('admin123')  # Change this password!
            admin_user.account_size = 10000.0  # $10,000 account
            
            db.session.add(admin_user)
            
            try:
                # Commit the user first to get the ID
                db.session.commit()
                print("Admin user created! Username: admin, Password: admin123")
                
                # Now create default settings for admin user using the committed user's ID
                settings = UserSettings(
                    user_id=admin_user.id,
                    auto_analyze_trades=True,
                    analysis_detail_level='detailed',
                    default_risk_percent=2.0
                )
                db.session.add(settings)
                db.session.commit()
                print("Admin user settings created successfully!")
                print("Please change the admin password after first login!")
                
            except Exception as e:
                db.session.rollback()
                print(f"Error creating admin user: {e}")

if __name__ == '__main__':
    # Import the original app after creating the Flask app
    app = create_app()
    
    # Initialize database
    init_database(app)
    
    # Import routes from the original app file
    from app_original import *
    
    # Run the application
    print("Starting AI Trading Analysis Application...")
    print("Default admin login: username='admin', password='admin123'")
    print("Application running at: http://localhost:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000) 