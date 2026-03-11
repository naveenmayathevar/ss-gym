import random
from datetime import datetime, timedelta
from run import app
from app import db
# Make sure this import matches where your GymClass model lives!
from app.models.fitness import GymClass

def seed_classes():
    titles = ['HIIT Blast', 'Power Yoga', 'Spin City', 'Zumba Party', 'CrossFit Fundamentals', 'Pilates Core', 'Boxing Bootcamp', 'Kettlebell Crush']
    instructors = ['Sarah', 'Mike', 'Emma', 'David', 'Alex', 'Jessica', 'Ryan', 'Lisa']
    
    with app.app_context():
        for i in range(20):
            title = random.choice(titles)
            instructor = random.choice(instructors)
            
            # Pick a random day in the next 14 days, and a random hour between 6 AM and 7 PM
            days_ahead = random.randint(1, 14)
            hour = random.randint(6, 19)
            sched = (datetime.now() + timedelta(days=days_ahead)).replace(hour=hour, minute=0)
            
            new_class = GymClass(
                title=title, 
                instructor=instructor, 
                schedule_time=sched, # e.g., March 12, 2026 at 06:00 PM
                capacity=20
            )
            db.session.add(new_class)
            
        db.session.commit()
        print("*** 20 RANDOM CLASSES SUCCESSFULLY ADDED! ***")

if __name__ == "__main__":
    seed_classes()