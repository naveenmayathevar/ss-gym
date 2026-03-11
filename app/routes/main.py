from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, session, jsonify

# ... your other imports ...
from flask_login import login_required, current_user
from app import db
from app.models.fitness import GymClass, Booking
import os
from werkzeug.utils import secure_filename
import stripe
import os
from datetime import datetime
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    # If they are already logged in, skip the landing page and go to the dashboard!
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    # If they are a guest, show them the sales pitch
    return render_template('index.html')

# ---> UPDATED: Paginated Classes <---
@main_bp.route('/classes')
def classes():
    # Get the search query and the current page number from the URL (default to page 1)
    search_query = request.args.get('q')
    page = request.args.get('page', 1, type=int)
    
    if search_query:
        # Filter by search and paginate (6 items per page)
        pagination = GymClass.query.filter(GymClass.title.ilike(f'%{search_query}%')).paginate(page=page, per_page=6, error_out=False)
    else:
        # No search, just paginate everything
        pagination = GymClass.query.paginate(page=page, per_page=6, error_out=False)
        
    return render_template('classes.html', pagination=pagination, search_query=search_query)

# ---> NEW: Handle the booking action <---
# ---> NEW: Handle the booking action <---
@main_bp.route('/book/<int:class_id>', methods=['POST'])
@login_required
def book_class(class_id):
    
    # THE BOUNCER CHECK: If they are NOT premium AND they have NO passes, kick them out.
    if not current_user.is_premium and current_user.class_passes <= 0:
        flash('You need a Premium Membership or a Class Pass to book.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    gym_class = GymClass.query.get_or_404(class_id)
    
    # Duplicate check
    existing_booking = Booking.query.filter_by(user_id=current_user.id, class_id=class_id).first()
    if existing_booking:
        flash('You have already booked this class!', 'warning')
        return redirect(url_for('main.dashboard'))

    # Capacity check
    current_bookings_count = Booking.query.filter_by(class_id=class_id).count()
    if current_bookings_count >= gym_class.capacity:
        flash('Sorry, this class is fully booked!', 'danger')
        return redirect(url_for('main.classes'))
    
    # Book the class
    new_booking = Booking(user_id=current_user.id, class_id=class_id)
    db.session.add(new_booking)
    
    # THE TICKET RIPPER: Deduct a pass if they are not premium
    if not current_user.is_premium:
        current_user.class_passes -= 1
        
    db.session.commit()
    
    flash(f'Successfully booked {gym_class.title}!', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    now = datetime.now()
    
    upcoming_bookings = []
    past_bookings = []
    
    all_bookings = Booking.query.filter_by(user_id=current_user.id).all()
    
    for booking in all_bookings:
        # --- THE DOCKER FIX: Intercept the string and convert it! ---
        if isinstance(booking.gym_class.schedule_time, str):
            try:
                # Convert the text string into a real ticking datetime object
                booking.gym_class.schedule_time = datetime.fromisoformat(booking.gym_class.schedule_time)
            except ValueError:
                # If the string is totally unreadable, default it to a past date
                booking.gym_class.schedule_time = datetime(2000, 1, 1)
        # ------------------------------------------------------------

        if booking.gym_class.schedule_time >= now:
            upcoming_bookings.append(booking)
        else:
            past_bookings.append(booking)
            
    return render_template('dashboard.html', 
                           upcoming_bookings=upcoming_bookings, 
                           past_bookings=past_bookings)
# ---> NEW: The Admin Dashboard <---
# ---> NEW: The Admin Dashboard <---
@main_bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    # The Bouncer: If they aren't an admin, kick them out with a 403 Forbidden error!
    if current_user.role != 'admin':
        abort(403) 
        
    # If the admin submits the "Add Class" form...
    if request.method == 'POST':
        title = request.form.get('title')
        instructor = request.form.get('instructor')
        
        # 1. Grab the raw string from the calendar picker (e.g., '2026-03-20T07:00')
        raw_time = request.form.get('schedule_time')
        
        # 2. Translate that string into a real Python datetime object!
        try:
            # This tells Python exactly how to read the HTML calendar format
            clean_time = datetime.strptime(raw_time, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format!', 'danger')
            return redirect(url_for('main.admin'))

        # Grab the capacity from the form, default to 20 if something goes wrong
        capacity = int(request.form.get('capacity', 20)) 
        
        # 3. Pass the CLEAN datetime object into the database
        new_class = GymClass(title=title, instructor=instructor, schedule_time=clean_time, capacity=capacity)
        db.session.add(new_class)
        db.session.commit()
        
        flash(f'Successfully added {title} to the schedule!', 'success')
        return redirect(url_for('main.admin'))
        
    # Show the admin page
    all_classes = GymClass.query.all()
    return render_template('admin.html', classes=all_classes)
@main_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    plan = request.form.get('plan', 'premium') 
    session['plan'] = plan
    
    # 1. Set the correct price and name based on what they clicked!
    if plan == 'single':
        amount = 1500  # $15.00 in cents
        product_name = 'Single Class Pass'
        product_desc = 'Good for any one class on the schedule'
    else:
        amount = 4999  # $49.99 in cents
        product_name = 'Premium Gym Membership'
        product_desc = 'Unlimited access to all classes'

    try:
        # 2. Ask Stripe to generate the page using our dynamic variables
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': amount, # <-- Uses the dynamic amount!
                        'product_data': {
                            'name': product_name, # <-- Uses the dynamic name!
                            'description': product_desc,
                        },
                    },
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=url_for('main.payment_success', _external=True),
            cancel_url=url_for('main.dashboard', _external=True),
        )
        
        return redirect(checkout_session.url, code=303)
        
    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('main.dashboard'))

# A quick success page for when they return!
@main_bp.route('/payment-success')
@login_required
def payment_success():
    # 2. Check the session to see what they bought
    plan = session.get('plan')
    
    if plan == 'single':
        current_user.class_passes += 1
        flash('Payment successful! 1 Class Pass added to your account.', 'success')
    else:
        current_user.is_premium = True
        flash('Payment successful! Your Premium Membership is now active.', 'success')
        
    db.session.commit()
    return redirect(url_for('main.dashboard'))
# ---> NEW: Delete a class <---
@main_bp.route('/admin/delete/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    if current_user.role != 'admin':
        abort(403)
        
    gym_class = GymClass.query.get(class_id)
    if gym_class:
        # First, delete all bookings for this class so the database doesn't crash
        Booking.query.filter_by(class_id=class_id).delete()
        # Then delete the class itself
        db.session.delete(gym_class)
        db.session.commit()
        flash('Class deleted.', 'info')
        
    return redirect(url_for('main.admin'))

# ---> NEW: Profile Settings <---
@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # Update text info
        current_user.name = request.form.get('name')
        current_user.fitness_goal = request.form.get('fitness_goal')
        
        # ---> NEW: Handle Image Upload <---
        file = request.files.get('profile_pic')
        if file and file.filename != '':
            # Clean the filename to prevent hackers from uploading malicious scripts
            filename = secure_filename(file.filename)
            # Add the user's ID to the front so names don't clash (e.g., 1_photo.jpg)
            unique_name = f"{current_user.id}_{filename}"
            
            # Tell Python exactly where to save it (app/static/uploads)
            upload_path = os.path.join('app', 'static', 'uploads')
            os.makedirs(upload_path, exist_ok=True) # Create folder if it doesn't exist
            
            # Save the actual file to the hard drive
            file.save(os.path.join(upload_path, unique_name))
            
            # Save just the filename to the database
            current_user.avatar_file = unique_name
            
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('main.dashboard'))
        
    return render_template('settings.html')

# ---> NEW: View Class Roster <---
@main_bp.route('/admin/roster/<int:class_id>')
@login_required
def roster(class_id):
    if current_user.role != 'admin':
        abort(403)
        
    gym_class = GymClass.query.get_or_404(class_id)
    return render_template('roster.html', gym_class=gym_class)

# ---> NEW: Cancel a Booking <---
@main_bp.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    # Find the booking in the database
    booking = Booking.query.get_or_404(booking_id)
    
    # Security check: Make sure the logged-in user actually owns this booking!
    if booking.user_id != current_user.id:
        flash("You cannot cancel someone else's class!", "danger")
        return redirect(url_for('main.dashboard'))
        
    # Delete it and save the database
    db.session.delete(booking)
    db.session.commit()
    
    flash('Your booking has been successfully cancelled.', 'info')
    return redirect(url_for('main.dashboard'))
# ---> NEW: Custom 404 Error Page <---
@main_bp.app_errorhandler(404)
def page_not_found(e):
    # Notice the ', 404' at the end? That tells the browser it's officially an error code
    return render_template('404.html'), 404
@main_bp.route('/cancel-membership', methods=['POST'])
@login_required
def cancel_membership():
    # Only cancel if they actually have a membership!
    if current_user.is_premium:
        current_user.is_premium = False
        db.session.commit()
        flash('Your Premium Membership has been canceled.', 'info')
    else:
        flash('You do not have an active Premium Membership to cancel.', 'warning')
        
    return redirect(url_for('main.dashboard'))
@main_bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '').lower()
    
    # --- ADD YOUR PHONE NUMBER HERE ---
    # Must include country code, no +, no dashes (e.g., 1 for US: 15551234567)
    whatsapp_number = "+14804629181" 
    whatsapp_link = f"https://wa.me/{whatsapp_number}?text=Hi%20SS%20Fitness!%20I%20need%20some%20help."

    if 'hours' in user_message or 'open' in user_message:
        bot_reply = "We are open 24/7 for Premium members! Staffed hours are 6:00 AM to 10:00 PM daily."
    elif 'book' in user_message or 'class' in user_message:
        bot_reply = "You can book a class on the 'Classes' page. Make sure you have a Class Pass or a Premium Membership!"
    elif 'cancel' in user_message or 'refund' in user_message:
        bot_reply = "You can cancel a class right from your Dashboard. If you used a Single Class Pass, it will be automatically refunded to your account."
    
    # --- THE NEW WHATSAPP RULE ---
    elif 'human' in user_message or 'contact' in user_message or 'whatsapp' in user_message or 'help' in user_message:
        bot_reply = f'I can connect you to our staff! <a href="{whatsapp_link}" target="_blank" class="text-warning fw-bold text-decoration-underline">Click here to chat with us on WhatsApp.</a>'
    
    elif 'hi' in user_message or 'hello' in user_message:
        bot_reply = "Hi there! I'm the SS Fitness Bot. How can I help you crush your goals today?"
    else:
        bot_reply = "I'm just a simple bot and I'm still learning! Try asking me about our 'hours', 'classes', or ask for a 'human' to get our WhatsApp."

    return jsonify({'reply': bot_reply})


