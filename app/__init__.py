from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from app.config import Config

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Attach extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Setup Login Manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Load the models so Flask and Flask-Login know about them
    from app.models.user import User
    from app.models.fitness import GymClass, Booking

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # A simple test route
    @app.route('/ping')
    def ping():
        return {"status": "success", "message": "SS Fitness API is running!"}

    # Register our Auth Blueprint
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Register our Main Blueprint
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    return app