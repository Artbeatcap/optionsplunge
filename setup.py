#!/usr/bin/env python3
"""
Setup script for AI Trading Analysis Application
"""

import os
import subprocess
import sys

def create_env_file():
    """Create a .env file with default settings"""
    env_content = """# Flask Configuration
SECRET_KEY=dev-secret-key-change-in-production
DEBUG=True
FLASK_ENV=development

# Database Configuration
DATABASE_URL=sqlite:///trading_app.db

# API Keys (Optional - add your own keys)
OPENAI_API_KEY=your-openai-api-key-here
TRADIER_API_TOKEN=fImjhesSMVWnq15UN5PWUvARApRX

# Email Configuration (Optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-email-password

# Application Settings
TRADES_PER_PAGE=20
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ Created .env file with default settings")
    else:
        print("ℹ️  .env file already exists, skipping creation")

def install_dependencies():
    """Install Python dependencies"""
    print("📦 Installing Python dependencies...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    directories = [
        'static/uploads',
        'static/css',
        'static/js'
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            print(f"✅ Created directory: {directory}")
        else:
            print(f"ℹ️  Directory already exists: {directory}")

def main():
    print("🚀 Setting up AI Trading Analysis Application")
    print("=" * 50)
    
    # Check if we're in the right directory
    required_files = ['app_original.py', 'models.py', 'requirements.txt', 'config.py']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        print("Please run this script from the application root directory")
        return False
    
    # Create .env file
    create_env_file()
    
    # Create directories
    create_directories()
    
    # Install dependencies
    if not install_dependencies():
        return False
    
    print("\n" + "=" * 50)
    print("🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Edit the .env file to add your API keys (optional)")
    print("2. Run the application: python app.py")
    print("3. Open http://localhost:5000 in your browser")
    print("4. Login with username: admin, password: admin123")
    print("5. Change the admin password after first login!")
    print("\n📖 Read README.md for detailed instructions")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 