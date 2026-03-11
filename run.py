from app import create_app
from flask_migrate import upgrade  # <--- You need this line right here!

app = create_app()

with app.app_context():
    upgrade()

if __name__ == '__main__':
    # Runs the app on port 5000 and allows connections from anywhere (0.0.0.0)
    app.run(host='0.0.0.0', port=5000, debug=True)