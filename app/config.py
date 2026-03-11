import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-fallback-secret'
    # SQLAlchemy config
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False 
    
    # --- ADD THESE TWO LINES ---
    # We are using 'STRIPE_API_KEY' here to perfectly match what you typed in Render!
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_API_KEY') 
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')