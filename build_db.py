from app import create_app, db
from sqlalchemy import text
from app.models.user import User  # (Change 'user' to 'users' if your file is named users.py)

app = create_app()

with app.app_context():
    print("Cleaning up corrupted database tables...")
    db.drop_all()
    db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
    db.session.commit()
    
    print("Building fresh, perfect tables...")
    db.create_all()
    
    print("Generating Admin account...")
    admin = User(
        name="Gym Owner",
        email="naveenmayathevar@gmail.com",  # <-- Put your real email here!
        role="admin",
        is_premium=True
    )
    admin.set_password("Admin123!")         # <-- Your temporary password
    
    db.session.add(admin)
    db.session.commit()
    print("Success! Database is ready.")