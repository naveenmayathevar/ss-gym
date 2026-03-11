from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import hashlib

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user') # Can be 'user' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    fitness_goal = db.Column(db.String(200), nullable=True)
    avatar_file = db.Column(db.String(120), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)
    class_passes = db.Column(db.Integer, default=0)
    # These methods securely scramble the password so we never save plain text!
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def avatar(self, size):
        # 1. If they uploaded a custom image, use that!
        if self.avatar_file:
            return f'/static/uploads/{self.avatar_file}'
            
        # 2. Otherwise, fall back to the Gravatar generated image
        digest = hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)