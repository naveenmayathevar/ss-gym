"""
build_db.py — Safe database initializer for Render deployments.

WHAT THIS DOES:
- Creates tables if they don't exist (safe for production)
- Creates the admin account only if it doesn't already exist
- NEVER drops existing tables (your data is safe across deploys!)

The old version used DROP SCHEMA which wiped everything on every deploy.
"""
from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    print("Ensuring all database tables exist...")
    db.create_all()  # Only creates tables that are missing — never deletes data

    print("Checking for admin account...")
    admin_email = "naveenmayathevar@gmail.com"
    existing_admin = User.query.filter_by(email=admin_email).first()

    if not existing_admin:
        print("Creating admin account...")
        admin = User(
            name="Gym Owner",
            email=admin_email,
            role="admin",
            is_premium=True
        )
        admin.set_password("Admin123!")
        db.session.add(admin)
        db.session.commit()
        print("Admin account created successfully.")
    else:
        print("Admin account already exists — skipping.")

    print("Database is ready!")