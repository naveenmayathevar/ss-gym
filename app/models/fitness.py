from app import db
from datetime import datetime

class GymClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    instructor = db.Column(db.String(100), nullable=False)
    schedule_time = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, default=20)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to bookings
    bookings = db.relationship('Booking', backref='gym_class', lazy=True, cascade="all, delete-orphan")

    # ---> NEW: Smart Math Properties <---
    @property
    def spots_left(self):
        # Count how many bookings exist for this specific class ID
        booked_count = Booking.query.filter_by(class_id=self.id).count()
        return self.capacity - booked_count

    @property
    def fill_percentage(self):
        booked_count = Booking.query.filter_by(class_id=self.id).count()
        
        # Prevent a "divide by zero" error just in case capacity is 0
        if self.capacity == 0:
            return 0
            
        # Calculate the percentage and turn it into a solid integer (e.g., 85)
        return int((booked_count / self.capacity) * 100)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_class.id'), nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)