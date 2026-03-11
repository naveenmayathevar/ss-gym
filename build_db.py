from app import create_app, db
from sqlalchemy import text
from app.models.user import User 

app = create_app()

with app.app_context():
    print("Cleaning up corrupted database tables...")
    # The "Nuke it from orbit" command for PostgreSQL
    db.session.execute(text("DROP SCHEMA public CASCADE;"))
    db.session.execute(text("CREATE SCHEMA public;"))
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
    admin.set_password("Admin123!")         
    
    db.session.add(admin)
    db.session.commit()
    print("Success! Database is ready.")