from app import create_app, db
from flask_migrate import upgrade
from sqlalchemy import text
from app.models.user import User

app = create_app()

with app.app_context():
    try:
        # Try to run migrations normally
        upgrade()
    except Exception as e:
        # If it crashes, wipe the corrupted tables clean and try again!
        print(f"Database mismatch detected! Healing database... Error: {e}")
        db.session.rollback()
        db.drop_all()
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        upgrade()
        
    # ---> THE ADMIN HACK <---
    # Put the email you are ABOUT TO register with below!
    my_user = User.query.filter_by(email="naveenmayathevar@gmail.com").first()
    
    if my_user and my_user.role != 'admin':
        my_user.role = 'admin'
        db.session.commit()
        print("Boom! Admin user promoted!")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)