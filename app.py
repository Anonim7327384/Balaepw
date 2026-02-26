from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'excursion_secret_key_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

USERS_FILE      = os.path.join(DATA_DIR, 'users.json')
EXCURSIONS_FILE = os.path.join(DATA_DIR, 'excursions.json')
BOOKINGS_FILE   = os.path.join(DATA_DIR, 'bookings.json')


def read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def next_id(items):
    return max((i['id'] for i in items), default=0) + 1


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Доступ запрещен', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    excursions = read_json(EXCURSIONS_FILE)
    featured = excursions[:3]
    return render_template('index.html', featured=featured)


@app.route('/catalog')
def catalog():
    excursions = read_json(EXCURSIONS_FILE)
    category   = request.args.get('category', '')
    search     = request.args.get('search', '').lower()

    if category:
        excursions = [e for e in excursions if e['category'] == category]
    if search:
        excursions = [e for e in excursions
                      if search in e['title'].lower() or search in e['description'].lower()]

    categories = sorted(set(e['category'] for e in read_json(EXCURSIONS_FILE)))
    return render_template('catalog.html', excursions=excursions,
                           categories=categories, selected_category=category, search=search)


@app.route('/excursion/<int:exc_id>')
def excursion(exc_id):
    excursions = read_json(EXCURSIONS_FILE)
    exc = next((e for e in excursions if e['id'] == exc_id), None)
    if not exc:
        flash('Экскурсия не найдена', 'danger')
        return redirect(url_for('catalog'))
    available = exc['seats_total'] - exc['seats_booked']
    return render_template('excursion.html', exc=exc, available=available)


@app.route('/book/<int:exc_id>', methods=['GET', 'POST'])
@login_required
def book(exc_id):
    excursions = read_json(EXCURSIONS_FILE)
    exc = next((e for e in excursions if e['id'] == exc_id), None)
    if not exc:
        return redirect(url_for('catalog'))

    available = exc['seats_total'] - exc['seats_booked']

    if request.method == 'POST':
        count      = int(request.form.get('count', 1))
        comment    = request.form.get('comment', '')
        child_name = request.form.get('child_name', '')

        if count < 1 or count > available:
            flash(f'Укажите количество от 1 до {available}', 'danger')
            return render_template('excursion.html', exc=exc, available=available, show_form=True)

        bookings = read_json(BOOKINGS_FILE)

        already = any(b for b in bookings
                      if b['user_id'] == session['user_id'] and b['excursion_id'] == exc_id
                      and b['status'] != 'cancelled')
        if already:
            flash('Вы уже забронировали эту экскурсию', 'warning')
            return redirect(url_for('cabinet'))

        new_booking = {
            'id': next_id(bookings),
            'user_id': session['user_id'],
            'user_name': session['name'],
            'excursion_id': exc_id,
            'excursion_title': exc['title'],
            'excursion_date': exc['date'],
            'excursion_price': exc['price'],
            'count': count,
            'total_price': exc['price'] * count,
            'child_name': child_name,
            'comment': comment,
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        bookings.append(new_booking)
        write_json(BOOKINGS_FILE, bookings)

        for e in excursions:
            if e['id'] == exc_id:
                e['seats_booked'] += count
        write_json(EXCURSIONS_FILE, excursions)

        flash('Бронирование успешно оформлено! Ожидайте подтверждения.', 'success')
        return redirect(url_for('cabinet'))

    return render_template('excursion.html', exc=exc, available=available, show_form=True)


@app.route('/cabinet')
@login_required
def cabinet():
    bookings = read_json(BOOKINGS_FILE)
    my_bookings = [b for b in bookings if b['user_id'] == session['user_id']]
    users = read_json(USERS_FILE)
    user = next(u for u in users if u['id'] == session['user_id'])
    return render_template('cabinet.html', bookings=my_bookings, user=user)


@app.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    bookings   = read_json(BOOKINGS_FILE)
    excursions = read_json(EXCURSIONS_FILE)

    for b in bookings:
        if b['id'] == booking_id and b['user_id'] == session['user_id']:
            if b['status'] == 'cancelled':
                flash('Бронирование уже отменено', 'warning')
                break
            b['status'] = 'cancelled'
            for e in excursions:
                if e['id'] == b['excursion_id']:
                    e['seats_booked'] = max(0, e['seats_booked'] - b['count'])
            flash('Бронирование отменено', 'info')
            break

    write_json(BOOKINGS_FILE, bookings)
    write_json(EXCURSIONS_FILE, excursions)
    return redirect(url_for('cabinet'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        phone    = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        if not all([name, email, password, confirm]):
            flash('Заполните все обязательные поля', 'danger')
            return render_template('register.html')

        if password != confirm:
            flash('Пароли не совпадают', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'danger')
            return render_template('register.html')

        users = read_json(USERS_FILE)
        if any(u for u in users if u['email'] == email):
            flash('Пользователь с таким email уже существует', 'danger')
            return render_template('register.html')

        hashed = generate_password_hash(password)

        new_user = {
            'id': next_id(users),
            'name': name,
            'email': email,
            'phone': phone,
            'password': hashed,
            'role': 'user',
            'created_at': datetime.now().strftime('%Y-%m-%d')
        }
        users.append(new_user)
        write_json(USERS_FILE, users)

        session['user_id'] = new_user['id']
        session['name']    = new_user['name']
        session['role']    = new_user['role']

        flash(f'Добро пожаловать, {name}!', 'success')
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        users = read_json(USERS_FILE)
        user  = next((u for u in users if u['email'] == email), None)

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['name']    = user['name']
            session['role']    = user['role']
            flash(f'Добро пожаловать, {user["name"]}!', 'success')
            return redirect(url_for('admin') if user['role'] == 'admin' else url_for('index'))
        else:
            flash('Неверный email или пароль', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin():
    bookings   = read_json(BOOKINGS_FILE)
    excursions = read_json(EXCURSIONS_FILE)
    users      = read_json(USERS_FILE)

    stats = {
        'total_excursions': len(excursions),
        'total_bookings': len(bookings),
        'pending': sum(1 for b in bookings if b['status'] == 'pending'),
        'confirmed': sum(1 for b in bookings if b['status'] == 'confirmed'),
        'cancelled': sum(1 for b in bookings if b['status'] == 'cancelled'),
        'total_users': len([u for u in users if u['role'] == 'user']),
        'revenue': sum(b['total_price'] for b in bookings if b['status'] == 'confirmed'),
    }

    return render_template('admin.html', bookings=bookings,
                           excursions=excursions, stats=stats)


@app.route('/admin/booking/<int:booking_id>/<action>', methods=['POST'])
@admin_required
def admin_booking_action(booking_id, action):
    bookings = read_json(BOOKINGS_FILE)
    for b in bookings:
        if b['id'] == booking_id:
            if action == 'confirm':
                b['status'] = 'confirmed'
                flash('Бронирование подтверждено', 'success')
            elif action == 'cancel':
                b['status'] = 'cancelled'
                flash('Бронирование отклонено', 'info')
            break
    write_json(BOOKINGS_FILE, bookings)
    return redirect(url_for('admin'))


@app.route('/admin/excursion/add', methods=['GET', 'POST'])
@admin_required
def add_excursion():
    if request.method == 'POST':
        excursions = read_json(EXCURSIONS_FILE)
        new_exc = {
            'id': next_id(excursions),
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'location': request.form.get('location'),
            'date': request.form.get('date'),
            'duration': request.form.get('duration'),
            'price': int(request.form.get('price', 0)),
            'seats_total': int(request.form.get('seats_total', 10)),
            'seats_booked': 0,
            'image': request.form.get('image', ''),
            'age_group': request.form.get('age_group'),
            'category': request.form.get('category'),
        }
        excursions.append(new_exc)
        write_json(EXCURSIONS_FILE, excursions)
        flash('Экскурсия добавлена', 'success')
        return redirect(url_for('admin'))
    return render_template('add_excursion.html')


@app.route('/admin/excursion/edit/<int:exc_id>', methods=['GET', 'POST'])
@admin_required
def edit_excursion(exc_id):
    excursions = read_json(EXCURSIONS_FILE)
    exc = next((e for e in excursions if e['id'] == exc_id), None)
    if not exc:
        flash('Экскурсия не найдена', 'danger')
        return redirect(url_for('admin'))

    if request.method == 'POST':
        exc['title']       = request.form.get('title')
        exc['description'] = request.form.get('description')
        exc['location']    = request.form.get('location')
        exc['date']        = request.form.get('date')
        exc['duration']    = request.form.get('duration')
        exc['price']       = int(request.form.get('price', 0))
        exc['seats_total'] = int(request.form.get('seats_total', 10))
        exc['age_group']   = request.form.get('age_group')
        exc['category']    = request.form.get('category')
        image_val          = request.form.get('image', '').strip()
        if image_val:
            exc['image']   = image_val
        write_json(EXCURSIONS_FILE, excursions)
        flash('Экскурсия обновлена', 'success')
        return redirect(url_for('admin'))

    return render_template('edit_excursion.html', exc=exc)


@app.route('/admin/excursion/delete/<int:exc_id>', methods=['POST'])
@admin_required
def delete_excursion(exc_id):
    excursions = read_json(EXCURSIONS_FILE)
    excursions = [e for e in excursions if e['id'] != exc_id]
    write_json(EXCURSIONS_FILE, excursions)
    flash('Экскурсия удалена', 'info')
    return redirect(url_for('admin'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
