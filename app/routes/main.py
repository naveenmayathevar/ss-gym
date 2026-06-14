from flask import render_template, redirect, url_for, flash, request, abort, session, jsonify
from flask_openapi3 import APIBlueprint
from pydantic import BaseModel
from flask_login import login_required, current_user
from app import db
from app.models.fitness import GymClass, Booking
from app.services import cache
import os
from werkzeug.utils import secure_filename
import stripe
from datetime import datetime

class ClassPath(BaseModel):
    class_id: int
main_bp = APIBlueprint('main', __name__)


# ── Helper: serialize a GymClass to a plain dict ──────────────────────────────

def _serialize_class(c: GymClass) -> dict:
    """Convert a GymClass model to a JSON-safe dict."""
    return {
        'id':            c.id,
        'title':         c.title,
        'instructor':    c.instructor,
        'schedule_time': c.schedule_time.isoformat() if c.schedule_time else None,
        'capacity':      c.capacity,
        'spots_left':    c.spots_left,
        'fill_percentage': c.fill_percentage,
    }


# ── API routes (shown in Swagger) ─────────────────────────────────────────────

@main_bp.get('/api/classes')
def api_classes():
    """Get all gym classes (cached)"""
    # 1. Try the cache first
    cached = cache.get_class_list()
    if cached is not None:
        return jsonify(cached)

    # 2. Cache miss — hit the database
    classes = GymClass.query.order_by(GymClass.schedule_time).all()
    data = [_serialize_class(c) for c in classes]

    # 3. Store result in cache for next time
    cache.set_class_list(data)

    return jsonify(data)


@main_bp.get('/api/classes/<int:class_id>')
def api_class_detail(path: ClassPath):
    """Get a single gym class by ID (cached)"""
    class_id = path.class_id
    cached = cache.get_class_detail(class_id)
    if cached is not None:
        return jsonify(cached)
    gym_class = GymClass.query.get_or_404(class_id)
    data = _serialize_class(gym_class)
    cache.set_class_detail(class_id, data)
    return jsonify(data)


@main_bp.get('/api/classes/<int:class_id>/capacity')
def api_class_capacity(path: ClassPath):
    """Get spots remaining for a class (cached, short TTL)"""
    class_id = path.class_id
    cached = cache.get_class_capacity(class_id)
    if cached is not None:
        return jsonify({'class_id': class_id, 'spots_left': cached})
    gym_class = GymClass.query.get_or_404(class_id)
    spots = gym_class.spots_left
    cache.set_class_capacity(class_id, spots)
    return jsonify({'class_id': class_id, 'spots_left': spots})


# ── HTML routes (not in Swagger — that's fine) ────────────────────────────────

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')


@main_bp.route('/classes')
def classes():
    search_query = request.args.get('q')
    page = request.args.get('page', 1, type=int)

    if search_query:
        pagination = GymClass.query.filter(
            GymClass.title.ilike(f'%{search_query}%')
        ).paginate(page=page, per_page=6, error_out=False)
    else:
        pagination = GymClass.query.paginate(page=page, per_page=6, error_out=False)

    return render_template('classes.html', pagination=pagination, search_query=search_query)


@main_bp.route('/book/<int:class_id>', methods=['POST'])
@login_required
def book_class(class_id):
    if not current_user.is_premium and current_user.class_passes <= 0:
        flash('You need a Premium Membership or a Class Pass to book.', 'warning')
        return redirect(url_for('main.dashboard'))

    gym_class = GymClass.query.get_or_404(class_id)

    existing_booking = Booking.query.filter_by(user_id=current_user.id, class_id=class_id).first()
    if existing_booking:
        flash('You have already booked this class!', 'warning')
        return redirect(url_for('main.dashboard'))

    current_bookings_count = Booking.query.filter_by(class_id=class_id).count()
    if current_bookings_count >= gym_class.capacity:
        flash('Sorry, this class is fully booked!', 'danger')
        return redirect(url_for('main.classes'))

    new_booking = Booking(user_id=current_user.id, class_id=class_id)
    db.session.add(new_booking)

    if not current_user.is_premium:
        current_user.class_passes -= 1

    db.session.commit()

    # ── Invalidate cache: capacity changed ────────────────────────────────────
    cache.invalidate_class_cache(class_id=class_id)

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
        if isinstance(booking.gym_class.schedule_time, str):
            try:
                booking.gym_class.schedule_time = datetime.fromisoformat(booking.gym_class.schedule_time)
            except ValueError:
                booking.gym_class.schedule_time = datetime(2000, 1, 1)

        if booking.gym_class.schedule_time >= now:
            upcoming_bookings.append(booking)
        else:
            past_bookings.append(booking)

    return render_template('dashboard.html',
                           upcoming_bookings=upcoming_bookings,
                           past_bookings=past_bookings)


@main_bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if current_user.role != 'admin':
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title')
        instructor = request.form.get('instructor')
        raw_time = request.form.get('schedule_time')

        try:
            clean_time = datetime.strptime(raw_time, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format!', 'danger')
            return redirect(url_for('main.admin'))

        capacity = int(request.form.get('capacity', 20))
        new_class = GymClass(title=title, instructor=instructor,
                             schedule_time=clean_time, capacity=capacity)
        db.session.add(new_class)
        db.session.commit()

        # ── Invalidate cache: class list changed ──────────────────────────────
        cache.invalidate_class_cache()

        flash(f'Successfully added {title} to the schedule!', 'success')
        return redirect(url_for('main.admin'))

    all_classes = GymClass.query.all()
    return render_template('admin.html', classes=all_classes)


@main_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    plan = request.form.get('plan', 'premium')
    session['plan'] = plan

    if plan == 'single':
        amount = 1500
        product_name = 'Single Class Pass'
        product_desc = 'Good for any one class on the schedule'
    else:
        amount = 4999
        product_name = 'Premium Gym Membership'
        product_desc = 'Unlimited access to all classes'

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': amount,
                    'product_data': {
                        'name': product_name,
                        'description': product_desc,
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('main.payment_success', _external=True),
            cancel_url=url_for('main.dashboard', _external=True),
        )
        return redirect(checkout_session.url, code=303)

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('main.dashboard'))


@main_bp.route('/payment-success')
@login_required
def payment_success():
    plan = session.get('plan')

    if plan == 'single':
        current_user.class_passes += 1
        flash('Payment successful! 1 Class Pass added to your account.', 'success')
    else:
        current_user.is_premium = True
        flash('Payment successful! Your Premium Membership is now active.', 'success')

    db.session.commit()
    return redirect(url_for('main.dashboard'))


@main_bp.route('/admin/delete/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    if current_user.role != 'admin':
        abort(403)

    gym_class = GymClass.query.get(class_id)
    if gym_class:
        Booking.query.filter_by(class_id=class_id).delete()
        db.session.delete(gym_class)
        db.session.commit()

        # ── Invalidate cache: class removed ──────────────────────────────────
        cache.invalidate_class_cache(class_id=class_id)

        flash('Class deleted.', 'info')

    return redirect(url_for('main.admin'))


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.fitness_goal = request.form.get('fitness_goal')

        file = request.files.get('profile_pic')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_name = f"{current_user.id}_{filename}"
            upload_path = os.path.join('app', 'static', 'uploads')
            os.makedirs(upload_path, exist_ok=True)
            file.save(os.path.join(upload_path, unique_name))
            current_user.avatar_file = unique_name

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('settings.html')


@main_bp.route('/admin/roster/<int:class_id>')
@login_required
def roster(class_id):
    if current_user.role != 'admin':
        abort(403)

    gym_class = GymClass.query.get_or_404(class_id)
    return render_template('roster.html', gym_class=gym_class)


@main_bp.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash("You cannot cancel someone else's class!", "danger")
        return redirect(url_for('main.dashboard'))

    class_id = booking.class_id
    db.session.delete(booking)
    db.session.commit()

    # ── Invalidate cache: capacity changed ────────────────────────────────────
    cache.invalidate_class_cache(class_id=class_id)

    flash('Your booking has been successfully cancelled.', 'info')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/cancel-membership', methods=['POST'])
@login_required
def cancel_membership():
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

    whatsapp_number = "+14804629181"
    whatsapp_link = f"https://wa.me/{whatsapp_number}?text=Hi%20SS%20Fitness!%20I%20need%20some%20help."

    if 'hours' in user_message or 'open' in user_message:
        bot_reply = "We are open 24/7 for Premium members! Staffed hours are 6:00 AM to 10:00 PM daily."
    elif 'book' in user_message or 'class' in user_message:
        bot_reply = "You can book a class on the 'Classes' page. Make sure you have a Class Pass or a Premium Membership!"
    elif 'cancel' in user_message or 'refund' in user_message:
        bot_reply = "You can cancel a class right from your Dashboard. If you used a Single Class Pass, it will be automatically refunded to your account."
    elif 'human' in user_message or 'contact' in user_message or 'whatsapp' in user_message or 'help' in user_message:
        bot_reply = f'I can connect you to our staff! <a href="{whatsapp_link}" target="_blank" class="text-warning fw-bold text-decoration-underline">Click here to chat with us on WhatsApp.</a>'
    elif 'hi' in user_message or 'hello' in user_message:
        bot_reply = "Hi there! I'm the SS Fitness Bot. How can I help you crush your goals today?"
    else:
        bot_reply = "I'm just a simple bot and I'm still learning! Try asking me about our 'hours', 'classes', or ask for a 'human' to get our WhatsApp."

    return jsonify({'reply': bot_reply})