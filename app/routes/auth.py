from flask import Blueprint, render_template, request, redirect, url_for
from app import db
from app.models.user import User
from flask_login import login_user, logout_user, login_required

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # If the user submits the form...
    if request.method == 'POST':
        # Grab the data from the HTML form
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            return "Email already registered! Try logging in." # We'll make this prettier later
        
        # Create new user
        new_user = User(name=name, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # Send them to the login page
        return redirect(url_for('auth.login'))

    # If they are just visiting the page, show them the HTML template
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        # Verify credentials
        if user and user.check_password(password):
            login_user(user)
            # Send them to the home page!
            return redirect(url_for('main.index'))
            
        return "Invalid email or password" # We'll make this prettier later too
        
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))