from app import create_app

app = create_app()
with app.app_context():
    from app import db
    db.create_all()

if __name__ == '__main__':
    # Runs the app on port 5000 and allows connections from anywhere (0.0.0.0)
    app.run(host='0.0.0.0', port=5000, debug=True)