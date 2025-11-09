from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import mysql.connector
import hashlib
from functools import wraps

app = Flask(__name__)
app.secret_key = 'cinemadb'
DB_CONFIG = {
    'user': 'root',
    'password': '12340asz/',
    'host': '127.0.0.1',
    'database': 'cinemadb',
    'auth_plugin': 'mysql_native_password'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Помилка підключення до БД: {err}")
        return None


def hash_password(password):
        return hashlib.sha256(password.encode('utf-8')).hexdigest()


def check_password(hashed_password, user_password):
    return hashed_password == hashlib.sha256(user_password.encode('utf-8')).hexdigest()


@app.before_request
def load_logged_in_user():
    g.user = None
    user_id = session.get('user_id')

    if user_id is None:
        return
    conn = get_db_connection()

    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE idusers = %s", (user_id,))
            g.user = cursor.fetchone()
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(f"Помилка при завантаженні користувача: {err}")
            g.user = None
            conn.close()


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash('Ви повинні увійти, щоб побачити цю сторінку.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        if g.user['role'] != 'admin':
            flash('У вас немає прав доступу до цієї сторінки.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('Ім\'я користувача та пароль не можуть бути порожніми!', 'danger')
            return redirect(url_for('register'))

        conn = get_db_connection()
        if not conn:
            flash('Помилка сервера. Спробуйте пізніше.', 'danger')
            return render_template('register.html')

        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Це ім\'я користувача вже зайняте.', 'danger')
        else:
            hashed_pass = hash_password(password)
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'client')",
                           (username, hashed_pass))
            conn.commit()
            flash('Реєстрація успішна! Тепер ви можете увійти.', 'success')
            return redirect(url_for('login'))

        cursor.close()
        conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if not conn:
            flash('Помилка сервера. Спробуйте пізніше.', 'danger')
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password(user['password'], password):
            session.clear()
            session['user_id'] = user['idusers']
            session['role'] = user['role']
            flash(f'Вітаємо, {user["username"]}!', 'success')

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Неправильний логін або пароль.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('index'))


@app.route('/')
def index():
    conn = get_db_connection()
    if not conn:
        return "Помилка: не вдалося підключитися до бази даних.", 500

    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT s.idsessions, s.start_time, s.price, f.title, f.poster_url, h.name as hall_name
        FROM sessions s
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.idhalls
        WHERE s.start_time > NOW()
        ORDER BY s.start_time;
    """
    cursor.execute(query)
    sessions_list = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('index.html', sessions=sessions_list)



@app.route('/session/<int:session_id>')
@login_required
def session_detail(session_id):
    conn = get_db_connection()
    if not conn:
        flash("Критична помилка: Не вдалося підключитися до бази даних.", "danger")
        return redirect(url_for('index'))

    cursor = conn.cursor(dictionary=True)
    session_info = None
    all_seats = []
    taken_seats = set()

    try:
        query_session = """
            SELECT 
                s.idsessions, s.start_time, 
                h.name as hall_name, h.idhalls,
                f.*
            FROM sessions s
            JOIN films f ON s.film_id = f.id
            JOIN halls h ON s.hall_id = h.idhalls
            WHERE s.idsessions = %s;
        """
        cursor.execute(query_session, (session_id,))
        session_info = cursor.fetchone()

        if not session_info:
            flash('Сеанс не знайдено.', 'danger')
            return redirect(url_for('index'))

        cursor.execute(
            "SELECT * FROM hall_seats_map WHERE hall_id = %s ORDER BY `row_number`, seat_number",
            (session_info['idhalls'],)
        )
        all_seats = cursor.fetchall()

        cursor.execute(
            "SELECT seat_map_id FROM tickets WHERE session_id = %s AND status IN ('booked', 'paid')",
            (session_id,)
        )
        taken_seats_raw = cursor.fetchall()
        taken_seats = {seat['seat_map_id'] for seat in taken_seats_raw}

    except mysql.connector.Error as err:
        flash(f"Помилка бази даних при завантаженні сеансу: {err}", "danger")
        return redirect(url_for('index'))
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

    seats_by_row = {}
    for seat in all_seats:
        row = seat['row_number']
        if row not in seats_by_row:
            seats_by_row[row] = []
        seats_by_row[row].append(seat)

    return render_template('session_detail.html', session=session_info, seats_by_row=seats_by_row,
                           taken_seats=taken_seats)


@app.route('/book_ticket', methods=['POST'])
@login_required
def book_ticket():
    session_id = request.form.get('session_id')
    seat_map_id = request.form.get('seat_map_id')
    user_id = session.get('user_id')

    if not session_id or not seat_map_id or not user_id:
        flash('Помилка бронювання. Спробуйте ще раз.', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash('Помилка сервера. Спробуйте пізніше.', 'danger')
        return redirect(url_for('session_detail', session_id=session_id))

    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO tickets (session_id, user_id, seat_map_id, status)
            VALUES (%s, %s, %s, 'paid');
        """
        cursor.execute(query, (session_id, user_id, seat_map_id))
        conn.commit()
        flash('Квиток успішно придбано!', 'success')

    except mysql.connector.Error as err:
        conn.rollback()
        if err.errno == 1062:
            flash('Це місце вже зайняте. Будь ласка, оберіть інше.', 'danger')
        else:
            flash(f'Виникла помилка: {err}', 'danger')

    cursor.close()
    conn.close()

    return redirect(url_for('account'))


@app.route('/account')
@login_required
def account():
    user_id = session.get('user_id')

    conn = get_db_connection()
    if not conn:
        flash('Не вдалося завантажити квитки. Помилка підключення.', 'danger')
        return render_template('account.html', tickets=[])

    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 
            t.idtickets, t.status, t.purchase_date,
            f.title, s.start_time, h.name as hall_name,
            m.row_number, m.seat_number, s.price
        FROM tickets t
        JOIN users u ON t.user_id = u.idusers
        JOIN sessions s ON t.session_id = s.idsessions
        JOIN films f ON s.film_id = f.id
        JOIN hall_seats_map m ON t.seat_map_id = m.id_seats
        JOIN halls h ON m.hall_id = h.idhalls
        WHERE t.user_id = %s
        ORDER BY s.start_time DESC;
    """

    cursor.execute(query, (user_id,))
    my_tickets = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('account.html', tickets=my_tickets)


@app.route('/cancel_ticket/<int:ticket_id>', methods=['POST'])
@login_required
def cancel_ticket(ticket_id):
    conn = get_db_connection()
    if not conn:
        flash('Помилка сервера. Спробуйте пізніше.', 'danger')
        return redirect(url_for('account'))

    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT user_id, session_id FROM tickets WHERE idtickets = %s", (ticket_id,))
        ticket = cursor.fetchone()

        if not ticket:
            flash('Квиток не знайдено.', 'warning')
        elif ticket['user_id'] != g.user['idusers']:
            flash('У вас немає прав для скасування цього квитка.', 'danger')
        else:
            cursor.execute("DELETE FROM tickets WHERE idtickets = %s", (ticket_id,))
            conn.commit()
            flash('Ваше бронювання успішно скасовано.', 'success')

    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Помилка при скасуванні: {err}', 'danger')

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('account'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')


@app.route('/admin/add_film', methods=['GET', 'POST'])
@admin_required
def admin_add_film():
    if request.method == 'POST':
        title = request.form['title']
        genre = request.form['genre']
        duration = request.form['duration']
        description = request.form['description']
        release_date = request.form['release_date']
        poster_url = request.form['poster_url']

        conn = get_db_connection()
        if not conn:
            flash('Помилка сервера. Спробуйте пізніше.', 'danger')
            return render_template('admin_add_film.html')

        cursor = conn.cursor()
        query = """
            INSERT INTO films (title, genre, duration, description, release_date, poster_url)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        cursor.execute(query, (title, genre, duration, description, release_date, poster_url))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Фільм успішно додано!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_film.html')


@app.route('/admin/add_hall', methods=['GET', 'POST'])
@admin_required
def admin_add_hall():
    if request.method == 'POST':
        name = request.form['name']
        row_count = int(request.form['row_count'])
        seats_per_row = int(request.form['seats_per_row'])

        if not name or row_count <= 0 or seats_per_row <= 0:
            flash('Некоректні дані. Кількість рядів та місць має бути > 0.', 'danger')
            return render_template('admin_add_hall.html')

        conn = get_db_connection()
        if not conn:
            flash('Помилка сервера. Спробуйте пізніше.', 'danger')
            return render_template('admin_add_hall.html')

        cursor = conn.cursor()

        try:

            cursor.execute(
                "INSERT INTO halls (name, `row`, seats) VALUES (%s, %s, %s)",
                (name, row_count, seats_per_row)
            )

            new_hall_id = cursor.lastrowid

            cursor.callproc('autofill_hall', (new_hall_id, row_count, seats_per_row))

            conn.commit()
            flash(f'Зал "{name}" (схема: {row_count}x{seats_per_row}) успішно створено та заповнено.', 'success')

        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Помилка при створенні залу: {err}', 'danger')

        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_hall.html')


@app.route('/admin/add_session', methods=['GET', 'POST'])
@admin_required
def admin_add_session():
    conn = get_db_connection()
    if not conn:
        flash('Помилка сервера. Спробуйте пізніше.', 'danger')
        return render_template('admin_add_session.html', films=[], halls=[])

    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        film_id = request.form['film_id']
        hall_id = request.form['hall_id']
        start_time = request.form['start_time']
        price = request.form['price']

        query = """
            INSERT INTO sessions (film_id, hall_id, start_time, price)
            VALUES (%s, %s, %s, %s);
        """
        try:
            cursor.execute(query, (film_id, hall_id, start_time, price))
            conn.commit()
            flash('Сеанс успішно додано!', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Помилка додавання сеансу: {err}', 'danger')

        cursor.close()
        conn.close()

        return redirect(url_for('admin_dashboard'))

    try:
        cursor.execute("SELECT id, title FROM films ORDER BY title;")
        films = cursor.fetchall()

        cursor.execute("SELECT idhalls, name FROM halls ORDER BY name;")
        halls = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f'Помилка завантаження даних: {err}', 'danger')
        films = []
        halls = []

    cursor.close()
    conn.close()

    return render_template('admin_add_session.html', films=films, halls=halls)


if __name__ == '__main__':
    app.run(debug=True)
