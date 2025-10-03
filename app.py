from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_bcrypt import Bcrypt 
import pymysql.cursors 
from flaskext.mysql import MySQL
from functools import wraps
from datetime import datetime
import math # Importação de math para paginação
from flask import send_from_directory
import os
from werkzeug.utils import secure_filename 
# ----------------------------------------------------

MYSQL_HOST = 'localhost'      
MYSQL_USER = 'root'           
MYSQL_PASSWORD = ''           
MYSQL_DB = 'Mech_Control'     
# ----------------------------------------

app = Flask(__name__)

app.config['MYSQL_DATABASE_HOST'] = MYSQL_HOST
app.config['MYSQL_DATABASE_USER'] = MYSQL_USER
app.config['MYSQL_DATABASE_PASSWORD'] = MYSQL_PASSWORD
app.config['MYSQL_DATABASE_DB'] = MYSQL_DB

mysql = MySQL(app) 
app.secret_key = 'gabriellebertocchipenapolis' 
bcrypt = Bcrypt(app)
# --------------------------------------------------------

UPLOAD_FOLDER = 'static/uploads/diagnostics' 
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    if not filename:
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# ---------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session: 
            flash('Please log in to view this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'loggedin' not in session:
                flash('Please log in to view this page.', 'danger')
                return redirect(url_for('login'))
            
            user_role = session.get('role')

            if user_role == 'Manager':
                return f(*args, **kwargs)

            if user_role not in allowed_roles:
                flash(f'Access denied. Your role ({user_role}) does not permit this action.', 'danger')
                return redirect(url_for('home')) 

            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/sw.js')
def serve_service_worker():
    return send_from_directory(app.root_path, 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')
# ---------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']

        conn = mysql.get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cursor.fetchone()
        cursor.close()

        if account and bcrypt.check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            session['role'] = account['role']
            session['name'] = account.get('name', account['username']) 
            return redirect(url_for('home'))
        else:
            msg = 'Incorrect username or password!'
            
    return render_template('login.html', error=msg)

@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'Mechanic') 
        
        if not username or not password or not email or not name:
            msg = 'Please fill out all fields!'
            flash(msg, 'error')
            return render_template('register.html', msg=msg)

        conn = mysql.get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = %s OR email = %s', (username, email))
        account = cursor.fetchone()
        
        if account:
            msg = 'Account already exists with that Username or Email!'
            flash(msg, 'error')
        else:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

            
            sql = "INSERT INTO users (name, email, username, password, role) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (name, email, username, hashed_password, role))
            
            conn.commit()
            msg = 'You have successfully registered! Please login.'
            flash(msg, 'success')
            return redirect(url_for('login'))
        
        cursor.close()
        
    return render_template('register.html', msg=msg)

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('role', None) 
    session.pop('name', None) 
    
    flash('You have successfully logged out.', 'info') 
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    sql = """
    SELECT 
        pr.id, 
        v.plate,                
        v.model,                
        pr.part_name AS part, 
        pr.status, 
        pr.request_date 
    FROM parts_requests pr      
    JOIN vehicles v ON pr.vehicle_id = v.id  
    ORDER BY pr.request_date DESC
    """
    
    cursor.execute(sql)
    all_requests = cursor.fetchall()
    
    recent_activity = all_requests[:3] 
    cursor.close()
    
    return render_template('home.html', requests=all_requests, recent_activity=recent_activity)

@app.route('/vehicles_search', methods=['GET'])
@login_required
def vehicles_search():
    search_term = request.args.get('search_term', '').strip().upper()

    if not search_term:
        return redirect(url_for('vehicles'))

    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("SELECT plate FROM vehicles WHERE plate = %s", (search_term,))
    vehicle_match = cursor.fetchone()
    cursor.close()

    if vehicle_match:
        flash(f"Vehicle {search_term} found. Redirecting to details.", 'success')
        return redirect(url_for('vehicle_details', plate=search_term))
    else:
        flash(f"No exact match found for plate {search_term}. Showing partial results.", 'info')
        return redirect(url_for('vehicles', search_term=search_term))


@app.route('/add_diagnostic', methods=['GET', 'POST'])
@role_required(['Mechanic'])
def add_diagnostic():
    prefill_plate = request.args.get('plate', '').strip().upper() 
    
    if request.method == 'POST':
        plate = request.form.get('plate').strip().upper()
        new_diagnostic_notes = request.form.get('diagnostic_notes')
        
        conn = mysql.get_db()
        cursor = conn.cursor()
        
        photo_filename = None
        video_filename = None
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if 'photo_file' in request.files:
            photo = request.files['photo_file']
            if photo and allowed_file(photo.filename):
                filename = secure_filename(f"{plate}_{now.replace(' ', '_').replace(':', '')}_PHOTO_{photo.filename}")
                photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                photo.save(photo_path)
                photo_filename = os.path.join(app.config['UPLOAD_FOLDER'], filename).replace('\\', '/')

        if 'video_file' in request.files:
            video = request.files['video_file']
            if video and allowed_file(video.filename):
                filename = secure_filename(f"{plate}_{now.replace(' ', '_').replace(':', '')}_VIDEO_{video.filename}")
                video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                video.save(video_path)
                video_filename = os.path.join(app.config['UPLOAD_FOLDER'], filename).replace('\\', '/') 
        
        
        cursor.execute("SELECT diagnostic FROM vehicles WHERE plate = %s", (plate,))
        vehicle_data = cursor.fetchone()
        
        new_entry = f"\n\n--- Diagnostic Added on {now} ---"
        new_entry += f"\n{new_diagnostic_notes}"
        
        if photo_filename:
            new_entry += f"\n[MEDIA: Photo attached: /{photo_filename}]"
        if video_filename:
            new_entry += f"\n[MEDIA: Video attached: /{video_filename}]"
        
        
        if vehicle_data:
            current_diagnostic = vehicle_data[0] if vehicle_data[0] is not None else ""
            updated_diagnostic = current_diagnostic + new_entry
            
            sql = "UPDATE vehicles SET diagnostic = %s WHERE plate = %s"
            cursor.execute(sql, (updated_diagnostic, plate))
            flash(f'New diagnostic notes and media for plate {plate} APPENDED successfully!', 'success')
        
        else:
            initial_diagnostic = new_entry.strip() 
            sql = "INSERT INTO vehicles (plate, model, diagnostic) VALUES (%s, %s, %s)"
            cursor.execute(sql, (plate, 'New Entry (Manual)', initial_diagnostic))
            flash(f'New vehicle and initial diagnostic for plate {plate} registered successfully!', 'success')
        
        conn.commit()
        cursor.close()
        
        return redirect(url_for('vehicle_details', plate=plate))
        
    return render_template('add_diagnostic.html', prefill_plate=prefill_plate)


@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    flash("This search route is obsolete. Please use dedicated search or inbox pages.", 'warning')
    return redirect(url_for('home')) 


@app.route('/request_part', methods=['GET', 'POST'])
@login_required
def request_part():
    if request.method == 'POST':
        plate = request.form.get('plate').strip().upper()
        part_name = request.form.get('part_name')
        quantity = request.form.get('quantity')
        notes = request.form.get('notes')
        user_id = session.get('id')
        
        conn = mysql.get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM vehicles WHERE plate = %s", (plate,))
        vehicle_data = cursor.fetchone()
        
        if not vehicle_data:
            flash(f'Vehicle with plate {plate} not found. Please register it first.', 'danger')
            cursor.close()
            return redirect(url_for('request_part', prefill_plate=plate))
            
        vehicle_id = vehicle_data[0]
        
        sql = "INSERT INTO parts_requests (vehicle_id, part_name, quantity, notes, requested_by_user_id, status) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (vehicle_id, part_name, quantity, notes, user_id, 'Requested'))
        conn.commit()
        cursor.close()
        
        flash(f'Part request for "{part_name}" for plate {plate} submitted successfully!', 'success')
        return redirect(url_for('parts_inbox')) 
        
    prefill_plate = request.args.get('plate')
        
    return render_template('request_part.html', prefill_plate=prefill_plate)

@app.route('/parts_inbox')
@login_required
def parts_inbox():
    filter_status = request.args.get('status')
    search_term = request.args.get('search_term')

    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    sql = """
    SELECT 
        pr.id, v.plate, pr.part_name AS part, pr.status, pr.request_date, pr.quantity 
    FROM parts_requests pr
    JOIN vehicles v ON pr.vehicle_id = v.id
    """
    where_clauses = []
    params = []
    
    if filter_status:
        where_clauses.append("pr.status = %s")
        params.append(filter_status)
        
    if search_term:
        search_pattern = f'%{search_term}%'
        where_clauses.append("(v.plate LIKE %s OR pr.part_name LIKE %s)")
        params.extend([search_pattern, search_pattern])

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
        
    sql += " ORDER BY pr.request_date DESC"
    
    cursor.execute(sql, tuple(params))
    
    all_requests = cursor.fetchall()
    cursor.close()

    return render_template('parts_inbox.html', 
                           requests=all_requests,
                           current_status=filter_status,
                           current_search=search_term)

@app.route('/request_details/<int:request_id>', methods=['GET', 'POST'])
@login_required 
def request_details(request_id):
    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor) 
    
    if request.method == 'POST':
        allowed_to_update = ['Parts', 'Manager']
        if session.get('role') not in allowed_to_update:
            flash('Acesso negado. Apenas Parts e Manager podem atualizar o status.', 'danger')
            return redirect(url_for('request_details', request_id=request_id))
        
        new_status = request.form.get('status')
        if new_status:
            cursor.execute("UPDATE parts_requests SET status = %s WHERE id = %s", (new_status, str(request_id)))
            conn.commit()
            flash('Status do pedido atualizado com sucesso!', 'success')
            return redirect(url_for('request_details', request_id=request_id))


    sql_details = """
        SELECT 
            pr.*, 
            v.plate, 
            v.model, 
            u.username AS requested_by_username
        FROM parts_requests pr
        LEFT JOIN vehicles v ON pr.vehicle_id = v.id 
        LEFT JOIN users u ON pr.requested_by_user_id = u.id 
        WHERE pr.id = %s
    """
    
    cursor.execute(sql_details, (str(request_id),)) 
    request_data = cursor.fetchone()
    
    cursor.close()
    
    if not request_data or request_data.get('id') is None:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('parts_inbox'))
    
    return render_template('request_details.html', request=request_data)

@app.route('/vehicle_details/<string:plate>')
@login_required
def vehicle_details(plate):
    plate_upper = plate.upper()
    
    conn = mysql.get_db()
    
    cursor_v = conn.cursor(pymysql.cursors.DictCursor) 
    cursor_v.execute("SELECT * FROM vehicles WHERE plate = %s", (plate_upper,))
    vehicle_data = cursor_v.fetchone()
    cursor_v.close()

    cursor_r = conn.cursor(pymysql.cursors.DictCursor) 
    sql_requests = """
    SELECT id, part_name AS part, status, quantity 
    FROM parts_requests 
    WHERE vehicle_id = (SELECT id FROM vehicles WHERE plate = %s) 
    ORDER BY request_date DESC
    """
    cursor_r.execute(sql_requests, (plate_upper,))
    vehicle_requests = cursor_r.fetchall()
    cursor_r.close()
    
    if vehicle_data:
        details = {
            'plate': plate_upper,
            'model': vehicle_data.get('model', 'Model Unknown'),
            'diagnostic': vehicle_data.get('diagnostic', 'No diagnostic added.'),
            'part_requests': vehicle_requests
        }
    else:
        details = {
            'plate': plate_upper,
            'model': 'New Vehicle / Model Unknown',
            'diagnostic': f'No vehicle record found in the database for {plate_upper}.',
            'part_requests': vehicle_requests
        }

    return render_template('vehicle_details.html', details=details)

@app.route('/dashboard')
@login_required
def dashboard():
    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    sql = """
    SELECT 
        COUNT(*) AS total_vehicles,
        SUM(CASE WHEN diagnostic IS NULL OR diagnostic = '' THEN 1 ELSE 0 END) AS needs_diagnostic_count,
        SUM(CASE WHEN diagnostic IS NOT NULL AND diagnostic != '' THEN 1 ELSE 0 END) AS diagnostic_added_count
    FROM vehicles
    """
    
    cursor.execute(sql)
    counts = cursor.fetchone()
    cursor.close()
    
    return render_template('dashboard.html', 
        total_vehicles=counts.get('total_vehicles', 0),
        needs_diagnostic=counts.get('needs_diagnostic_count', 0),
        diagnostic_added=counts.get('diagnostic_added_count', 0),
        
        total=counts.get('total_vehicles', 0), 
        pending=0, ordered=0, delivered=0
    )

@app.route('/profile')
@login_required 
def profile():
    user_id = session.get('id')

    if not user_id:
        return redirect(url_for('login')) 

    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    cursor.execute("SELECT name, email, username, role FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()

    return render_template('profile.html', user_data=user_data)


@app.route('/vehicles')
@login_required
def vehicles():
    PER_PAGE = 10
    page = request.args.get('page', 1, type=int) 
    search_term = request.args.get('search_term', '').strip().upper()

    offset = (page - 1) * PER_PAGE 

    conn = mysql.get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    where_clause = ""
    params = []

    if search_term:
        where_clause = " WHERE plate LIKE %s OR diagnostic LIKE %s "
        search_pattern = f'%{search_term}%'
        params.extend([search_pattern, search_pattern])

    sql_vehicles = f"SELECT plate, model, diagnostic FROM vehicles {where_clause} ORDER BY plate ASC LIMIT %s OFFSET %s"
    params.extend([PER_PAGE, offset])
    cursor.execute(sql_vehicles, tuple(params))
    vehicles_on_page = cursor.fetchall()

    sql_count = f"SELECT COUNT(*) AS total FROM vehicles {where_clause}"
    count_params = params[:-2] 
    cursor.execute(sql_count, tuple(count_params))
    total_vehicles = cursor.fetchone()['total']
    
    cursor.close()

    total_pages = math.ceil(total_vehicles / PER_PAGE)

    return render_template('vehicles.html', 
                           vehicles=vehicles_on_page,
                           page=page,
                           total_pages=total_pages,
                           total_vehicles=total_vehicles,
                           current_search=search_term) 

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)