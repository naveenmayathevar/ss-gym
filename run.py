from app import create_app, db
from flask_migrate import upgrade
from app.models.user import User  # Make sure you import the User model!

app = create_app()

with app.app_context():
    upgrade()
    
    # ---> THE ADMIN HACK <---
    # Replace the email below with the exact email you registered with on your live site!
    my_user = User.query.filter_by(email="naveenmayathevar@gmail.com").first()
    
    if my_user and my_user.role != 'admin':
        my_user.role = 'admin'  # Giving you the admin role!
        db.session.commit()
        print("Boom! Admin user promoted!")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)