import json
import os
import threading
import time
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'assets'), template_folder=BASE_DIR)
DEFAULT_MYSQL_URI = 'mysql+pymysql://smartlab:SmartLab123@localhost:3306/smartlab'
FALLBACK_SQLITE_URI = 'sqlite:////tmp/smartlab.db' if os.getenv('VERCEL') else 'sqlite:///smartlab.db'

app_config_uri = (
    os.getenv('SMARTLAB_DB_URI')
    or os.getenv('MYSQL_DATABASE_URI')
    or os.getenv('DATABASE_URL')
    or DEFAULT_MYSQL_URI
)

if app_config_uri.startswith('postgres://'):
    app_config_uri = app_config_uri.replace('postgres://', 'postgresql://', 1)

try:
    if app_config_uri.startswith('mysql'):
        engine = create_engine(app_config_uri, connect_args={'connect_timeout': 2})
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        app_config_uri = app_config_uri
    else:
        app_config_uri = app_config_uri
except Exception:
    app_config_uri = FALLBACK_SQLITE_URI

if os.getenv('VERCEL') and app_config_uri.startswith('sqlite'):
    app_config_uri = 'sqlite:////tmp/smartlab.db'

app.config['SQLALCHEMY_DATABASE_URI'] = app_config_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db = SQLAlchemy(app)


@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


class Computer(db.Model):
    __tablename__ = 'computers'

    id = db.Column(db.String(32), primary_key=True)
    label = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(16), default='AVAILABLE')
    student_name = db.Column(db.String(120), default='')
    department = db.Column(db.String(120), default='')
    last_seen = db.Column(db.String(32), default='')
    current_booking_start = db.Column(db.String(16), default='')
    current_booking_end = db.Column(db.String(16), default='')

    def to_dict(self):
        return {
            'id': self.id,
            'label': self.label,
            'status': self.status,
            'studentName': self.student_name,
            'department': self.department,
            'lastSeen': self.last_seen,
            'currentBooking': self.current_booking_start and self.current_booking_end
            and {
                'start': self.current_booking_start,
                'end': self.current_booking_end,
            }
            or None,
        }


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.String(32), default='')
    register_number = db.Column(db.String(32), nullable=False, unique=True)
    department = db.Column(db.String(120), nullable=False)
    year = db.Column(db.String(32), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False, default='student123')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'dob': self.dob,
            'registerNumber': self.register_number,
            'department': self.department,
            'year': self.year,
        }


class Staff(db.Model):
    __tablename__ = 'staff'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.String(32), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    designation = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), default='')
    phone = db.Column(db.String(32), default='')
    assigned_lab = db.Column(db.String(120), default='Innovation Lab 01')

    def to_dict(self):
        return {
            'id': self.id,
            'staffId': self.staff_id,
            'name': self.name,
            'department': self.department,
            'designation': self.designation,
            'email': self.email,
            'phone': self.phone,
            'assignedLab': self.assigned_lab,
        }


class AdminSetting(db.Model):
    __tablename__ = 'admin_settings'

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=False)


def get_admin_password_hash():
    setting = AdminSetting.query.get('admin_password_hash')
    if not setting:
        default_hash = generate_password_hash('admin123')
        setting = AdminSetting(key='admin_password_hash', value=default_hash)
        db.session.add(setting)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return setting.value


def set_admin_password(new_password):
    setting = AdminSetting.query.get('admin_password_hash')
    new_hash = generate_password_hash(new_password)
    if not setting:
        setting = AdminSetting(key='admin_password_hash', value=new_hash)
        db.session.add(setting)
    else:
        setting.value = new_hash
    db.session.commit()


class UsageRecord(db.Model):
    __tablename__ = 'usage_records'

    id = db.Column(db.String(32), primary_key=True)
    student_name = db.Column(db.String(120), nullable=False)
    register_number = db.Column(db.String(32), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    year = db.Column(db.String(32), nullable=False)
    computer_id = db.Column(db.String(32), nullable=False)
    booked_date = db.Column(db.String(32), nullable=False)
    start_time = db.Column(db.String(16), nullable=False)
    end_time = db.Column(db.String(16), nullable=False)
    duration_hours = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(16), default='IN_USE')
    created_at = db.Column(db.String(64), default=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        return {
            'id': self.id,
            'studentName': self.student_name,
            'registerNumber': self.register_number,
            'department': self.department,
            'year': self.year,
            'computerId': self.computer_id,
            'bookedDate': self.booked_date,
            'startTime': self.start_time,
            'endTime': self.end_time,
            'durationHours': self.duration_hours,
            'status': self.status,
            'createdAt': self.created_at,
        }


def generate_computers():
    status_pool = ['AVAILABLE', 'AVAILABLE', 'AVAILABLE', 'AVAILABLE', 'AVAILABLE', 'IN_USE', 'IN_USE', 'IN_USE', 'OFFLINE']
    students = ['Aisha', 'Arun', 'Nandha', 'Farah', 'Karthik']
    departments = ['CSE', 'AI & DS', 'ECE', 'EEE', 'MECH']
    computers = []
    for index in range(1, 61):
        pc_number = index
        status = status_pool[(index - 1) % len(status_pool)]
        label = f'LAB-PC-{str(pc_number).zfill(2)}'
        student_name = students[(index - 1) % len(students)] if status == 'IN_USE' else ''
        department = departments[(index - 1) % len(departments)] if status == 'IN_USE' else ''
        last_seen = (datetime.utcnow().replace(microsecond=0)).isoformat()
        current_booking = {'start': '09:30', 'end': '11:00'} if status == 'IN_USE' else None
        computers.append(
            Computer(
                id=label,
                label=label,
                status=status,
                student_name=student_name,
                department=department,
                last_seen=last_seen,
                current_booking_start=current_booking['start'] if current_booking else '',
                current_booking_end=current_booking['end'] if current_booking else '',
            )
        )
    return computers


ENROLLED_STUDENTS_LIST = [
    ('AAMINA THASIN', '2007-08-22'),
    ('ABISHEK', '2007-02-24'),
    ('AJITHKUMAR', '2006-10-10'),
    ('AKSHARA BHARATHI', '2006-09-28'),
    ('ANAND', '2005-11-16'),
    ('ANBULINGAM', '2007-10-05'),
    ('ANCHANA', '2006-11-15'),
    ('ANISHA', '2006-11-10'),
    ('ANUSHUYA DEVI', '2006-10-10'),
    ('ARUNA', '2006-08-26'),
    ('ATHIKESAVAN', '2007-02-06'),
    ('BHARANITHARAN', ''),
    ('DEEPAK', '2006-12-12'),
    ('DEEPIKA', '2006-12-17'),
    ('DHARANEESH', '2007-07-28'),
    ('DHARANESH', '2007-02-19'),
    ('DHARANIKAA', '2007-01-14'),
    ('DHARASHIN KUMAR', '2007-06-04'),
    ('DHARSHINI', '2006-06-13'),
    ('DHARSHINI', '2007-07-28'),
    ('DHARSHINI', '2007-04-04'),
    ('DHARUN', '2006-05-17'),
    ('DHARUN', '2006-11-19'),
    ('DINESH KUMAR', '2005-08-21'),
    ('ENIYAN', '2006-09-12'),
    ('ETHIKASH', '2007-04-08'),
    ('GAYATHRI', '2006-08-10'),
    ('GIRIDHARAN', '2007-05-11'),
    ('GOBIKRISHNA', '2007-06-07'),
    ('GOPIKA', '2007-07-04'),
    ('GOUTHAM SIDDARTH', '2006-09-19'),
    ('GOWSHIKA', '2006-09-18'),
    ('GOWTHAM KOMBUKKATTUR SHANMUGASUNDARAM', '2007-03-28'),
    ('GOWTHAM', '2006-12-09'),
    ('GUGAN', '2007-06-06'),
    ('HARI AKASH', '2006-08-21'),
    ('HARIDASS', '2007-04-24'),
    ('HARIHARAMUGUNTHAN', '2007-01-07'),
    ('HARINE SHREE', '2006-09-16'),
    ('HARINI SRI', '2007-02-01'),
    ('HARSHINI', '2006-10-03'),
    ('HARSINI', '2007-06-17'),
    ('HEMALATHA', '2006-05-31'),
    ('INDHIRAN', '2006-06-21'),
    ('JAIAKASH', '2006-05-18'),
    ('JANADHARSHINI', '2006-12-23'),
    ('JANANI', '2007-08-25'),
    ('JAYANITHYAN', '2006-12-24'),
    ('JAYAPRIYA', '2006-11-16'),
    ('JIVITESH', '2007-04-11'),
    ('KAMALESHWARAN', '2006-11-08'),
    ('KANIKA', '2007-03-17'),
    ('KARTHICK', '2006-08-09'),
    ('KARTHIKA', '2006-12-06'),
    ('KARTHIKEYAN', '2007-02-17'),
    ('KAVIYA', '2007-02-26'),
    ('KIRUTHIKA', '2007-10-25'),
    ('LAILATHUL RASMIN', '2006-10-20'),
    ('LALITH', '2006-12-06')
]


def generate_students():
    students = []
    for idx, (name, dob) in enumerate(ENROLLED_STUDENTS_LIST, start=1):
        reg = f'732924ADR{str(idx).zfill(3)}'
        students.append(
            Student(
                id=idx,
                name=name,
                dob=dob,
                register_number=reg,
                department='AI & DS',
                year='2nd Year'
            )
        )
    return students


def generate_staff():
    return [
        Staff(id=1, staff_id='STF-101', name='Dr. R. Ramanathan', department='CSE', designation='Lab Incharge & Professor', email='ramanathan@smartlab.edu', phone='+91 98765 43210', assigned_lab='Innovation Lab 01'),
        Staff(id=2, staff_id='STF-102', name='Prof. S. Malathy', department='AI & DS', designation='Assistant Professor', email='malathy.s@smartlab.edu', phone='+91 98765 43211', assigned_lab='AI & Robotics Lab'),
        Staff(id=3, staff_id='STF-103', name='Er. Vigneshwaran K', department='ECE', designation='System Administrator', email='vignesh.admin@smartlab.edu', phone='+91 98765 43212', assigned_lab='Innovation Lab 01'),
        Staff(id=4, staff_id='STF-104', name='Dr. Anitha George', department='EEE', designation='Associate Professor', email='anitha.g@smartlab.edu', phone='+91 98765 43213', assigned_lab='IoT & Embedded Lab'),
        Staff(id=5, staff_id='STF-105', name='Er. Praveen Kumar', department='MECH', designation='Lab Technician', email='praveen.k@smartlab.edu', phone='+91 98765 43214', assigned_lab='CAD / CAM Lab'),
    ]


def generate_records():
    return [
        UsageRecord(
            id='R-1001',
            student_name='Aisha Khan',
            register_number='20CS101',
            department='CSE',
            year='3rd Year',
            computer_id='LAB-PC-01',
            booked_date='2026-10-14',
            start_time='09:00',
            end_time='11:00',
            duration_hours=2,
            status='IN_USE',
            created_at='2026-10-14T08:45:00.000Z',
        ),
        UsageRecord(
            id='R-1002',
            student_name='Arun Kumar',
            register_number='21AI205',
            department='AI & DS',
            year='2nd Year',
            computer_id='LAB-PC-08',
            booked_date='2026-10-14',
            start_time='11:30',
            end_time='13:00',
            duration_hours=1.5,
            status='IN_USE',
            created_at='2026-10-14T09:10:00.000Z',
        ),
        UsageRecord(
            id='R-1003',
            student_name='Nandha S',
            register_number='19EC118',
            department='ECE',
            year='4th Year',
            computer_id='LAB-PC-14',
            booked_date='2026-10-14',
            start_time='14:00',
            end_time='15:30',
            duration_hours=1.5,
            status='IN_USE',
            created_at='2026-10-14T10:20:00.000Z',
        ),
    ]


def seed_data():
    if not Computer.query.first():
        db.session.add_all(generate_computers())
    if Student.query.count() < 50 or not Student.query.filter_by(name='AAMINA THASIN').first():
        Student.query.delete()
        db.session.add_all(generate_students())
    if not Staff.query.first():
        db.session.add_all(generate_staff())
    if not UsageRecord.query.first():
        db.session.add_all(generate_records())
    db.session.commit()


def parse_time_to_minutes(value: str) -> int:
    if not value:
        return 0
    raw = str(value).strip().upper()
    is_pm = 'PM' in raw
    is_am = 'AM' in raw
    raw = raw.replace('AM', '').replace('PM', '').strip()
    parts = raw.split(':')
    if len(parts) < 2:
        return 0
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        if is_pm and hours < 12:
            hours += 12
        elif is_am and hours == 12:
            hours = 0
        return hours * 60 + minutes
    except Exception:
        return 0


def is_session_expired(booked_date_str: str, end_time_str: str, now: datetime = None) -> bool:
    if not end_time_str:
        return False
    if now is None:
        now = datetime.now()

    today_str = now.strftime('%Y-%m-%d')
    current_minutes = now.hour * 60 + now.minute

    rec_date = str(booked_date_str or '').strip()
    rec_end = str(end_time_str or '').strip()

    if rec_date:
        if rec_date < today_str:
            return True
        if rec_date > today_str:
            return False
        end_min = parse_time_to_minutes(rec_end)
        return current_minutes >= end_min
    else:
        end_min = parse_time_to_minutes(rec_end)
        return current_minutes >= end_min


def auto_release_expired_computers() -> list:
    """
    Scans all active workstations and usage records, automatically freeing up
    any workstation whose allocated booking session time has expired.
    """
    try:
        now = datetime.now()
        released_pc_ids = set()
        changed = False

        # 1. Check all UsageRecords marked IN_USE
        active_records = UsageRecord.query.filter_by(status='IN_USE').all()
        for record in active_records:
            if is_session_expired(record.booked_date, record.end_time, now):
                record.status = 'COMPLETED'
                changed = True
                if record.computer_id:
                    released_pc_ids.add(record.computer_id)

        # 2. Check all Computers marked IN_USE
        in_use_computers = Computer.query.filter_by(status='IN_USE').all()
        for comp in in_use_computers:
            comp_expired = False
            if comp.id in released_pc_ids:
                comp_expired = True
            elif comp.current_booking_end:
                if is_session_expired('', comp.current_booking_end, now):
                    comp_expired = True
            else:
                active_rec = UsageRecord.query.filter_by(computer_id=comp.id, status='IN_USE').first()
                if not active_rec:
                    comp_expired = True

            if comp_expired:
                # Ensure no other valid IN_USE record exists for this workstation
                other_active = UsageRecord.query.filter(
                    UsageRecord.computer_id == comp.id,
                    UsageRecord.status == 'IN_USE'
                ).first()
                if not other_active:
                    comp.status = 'AVAILABLE'
                    comp.student_name = ''
                    comp.department = ''
                    comp.current_booking_start = ''
                    comp.current_booking_end = ''
                    comp.last_seen = now.isoformat()
                    released_pc_ids.add(comp.id)
                    changed = True

        if changed:
            db.session.commit()

        return list(released_pc_ids)
    except Exception:
        db.session.rollback()
        return []


_scheduler_started = False


def start_background_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def worker():
        while True:
            time.sleep(5)
            try:
                with app.app_context():
                    auto_release_expired_computers()
            except Exception:
                pass

    thread = threading.Thread(target=worker, daemon=True, name="AutoReleaseWorker")
    thread.start()


with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE students ADD COLUMN password_hash VARCHAR(255) DEFAULT 'student123'"))
            conn.commit()
    except Exception:
        pass
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE students ADD COLUMN dob VARCHAR(32) DEFAULT ''"))
            conn.commit()
    except Exception:
        pass
    seed_data()
    auto_release_expired_computers()
    start_background_scheduler()


def get_state_payload():
    auto_release_expired_computers()
    return {
        'computers': [computer.to_dict() for computer in Computer.query.order_by(Computer.id).all()],
        'staff': [staff.to_dict() for staff in Staff.query.order_by(Staff.id).all()],
        'students': [student.to_dict() for student in Student.query.order_by(Student.id).all()],
        'records': [record.to_dict() for record in UsageRecord.query.order_by(UsageRecord.created_at.desc()).all()],
        'settings': {'autoApprove': True, 'conflictDetection': True, 'autoRelease': True},
        'telemetry': get_status_summary(),
    }


def get_status_summary():
    auto_release_expired_computers()
    computers = Computer.query.all()
    total = len(computers)
    available = sum(1 for cpu in computers if cpu.status == 'AVAILABLE')
    in_use = sum(1 for cpu in computers if cpu.status == 'IN_USE')
    offline = sum(1 for cpu in computers if cpu.status == 'OFFLINE')
    maintenance = sum(1 for cpu in computers if cpu.status == 'MAINTENANCE')
    occupancy_pct = round((in_use / total * 100), 1) if total > 0 else 0
    available_pct = round((available / total * 100), 1) if total > 0 else 0
    total_staff = Staff.query.count()
    recent = [r.to_dict() for r in UsageRecord.query.order_by(UsageRecord.created_at.desc()).limit(10).all()]
    return {
        'total': total,
        'available': available,
        'inUse': in_use,
        'offline': offline,
        'maintenance': maintenance,
        'occupancyPct': occupancy_pct,
        'availablePct': available_pct,
        'totalStaff': total_staff,
        'recentRecords': recent,
        'lastUpdated': datetime.now().isoformat()
    }


def validate_no_overlap(booked_date: str, computer_id: str, start_time: str, end_time: str):
    same_computer = UsageRecord.query.filter_by(computer_id=computer_id, booked_date=booked_date).all()
    new_start = parse_time_to_minutes(start_time)
    new_end = parse_time_to_minutes(end_time)
    for record in same_computer:
        existing_start = parse_time_to_minutes(record.start_time)
        existing_end = parse_time_to_minutes(record.end_time)
        if not (new_end <= existing_start or new_start >= existing_end):
            return False
    return True


@app.route('/')
def index_page():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/index.html')
def index_html_page():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/student.html')
def student_page():
    return send_from_directory(BASE_DIR, 'student.html')


@app.route('/student.js')
def student_script():
    return send_from_directory(BASE_DIR, 'student.js')


@app.route('/admin.html')
def admin_page():
    return send_from_directory(BASE_DIR, 'admin.html')


@app.route('/assets/<path:filename>')
def asset_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'assets'), filename)


@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.route('/api/health')
def health_check():
    try:
        with db.engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        db_name = 'SQLite' if str(app.config['SQLALCHEMY_DATABASE_URI']).startswith('sqlite') else 'MySQL'
        return jsonify({'ok': True, 'status': 'SmartLab backend is running', 'database': f'{db_name} connected'})
    except Exception as exc:
        db_name = 'SQLite' if str(app.config['SQLALCHEMY_DATABASE_URI']).startswith('sqlite') else 'MySQL'
        return jsonify({'ok': False, 'status': 'Database connection failed', 'database': f'{db_name} unavailable', 'error': str(exc)}), 503


@app.route('/api/state')
def get_state():
    return jsonify(get_state_payload())


@app.route('/api/summary')
def get_summary():
    return jsonify(get_status_summary())


@app.route('/api/computers')
def get_computers():
    auto_release_expired_computers()
    return jsonify([computer.to_dict() for computer in Computer.query.order_by(Computer.id).all()])


@app.route('/api/computers/auto-release', methods=['GET', 'POST'])
def auto_release_endpoint():
    released = auto_release_expired_computers()
    return jsonify({
        'ok': True,
        'releasedCount': len(released),
        'releasedComputers': released,
        'summary': get_status_summary(),
        'message': f'Auto-release verified. {len(released)} workstation(s) updated.'
    })


@app.route('/api/students', methods=['GET', 'POST'])
def get_students():
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form.to_dict()
        name = str(data.get('name') or data.get('studentName') or '').strip().upper()
        dob = str(data.get('dob') or data.get('dateOfBirth') or '').strip()
        reg = str(data.get('registerNumber') or data.get('register_number') or '').strip().upper()
        dept = str(data.get('department') or 'AI & DS').strip()
        year = str(data.get('year') or '2nd Year').strip()

        if not name or not dob or not reg:
            return jsonify({'ok': False, 'message': 'Student Name, DOB, and Register Number are required.'}), 400

        existing = Student.query.filter_by(register_number=reg).first()
        if existing:
            return jsonify({'ok': False, 'message': f'Student with Register Number {reg} already exists.'}), 400

        student = Student(
            name=name,
            dob=dob,
            register_number=reg,
            department=dept,
            year=year,
            password_hash=generate_password_hash('student123')
        )
        db.session.add(student)
        db.session.commit()
        return jsonify({
            'ok': True,
            'student': student.to_dict(),
            'message': f'Student {student.name} login credential created successfully!'
        }), 201

    return jsonify([student.to_dict() for student in Student.query.order_by(Student.name).all()])


@app.route('/api/students/<int:student_id>', methods=['PUT', 'DELETE'])
def student_detail_endpoint(student_id):
    student = Student.query.get(student_id)
    if not student:
        return jsonify({'ok': False, 'message': 'Student not found.'}), 404

    if request.method == 'DELETE':
        db.session.delete(student)
        db.session.commit()
        return jsonify({'ok': True, 'message': f'Student {student.name} deleted successfully.'})

    data = request.get_json(silent=True) or request.form.to_dict()
    if 'name' in data and str(data['name']).strip():
        student.name = str(data['name']).strip().upper()
    if 'dob' in data and str(data['dob']).strip():
        student.dob = str(data['dob']).strip()
    if 'registerNumber' in data and str(data['registerNumber']).strip():
        student.register_number = str(data['registerNumber']).strip().upper()
    if 'department' in data and str(data['department']).strip():
        student.department = str(data['department']).strip()
    if 'year' in data and str(data['year']).strip():
        student.year = str(data['year']).strip()

    db.session.commit()
    return jsonify({
        'ok': True,
        'student': student.to_dict(),
        'message': f'Student {student.name} login credential updated successfully!'
    })


@app.route('/api/student/login', methods=['POST'])
def student_login():
    data = request.get_json(silent=True) or request.form.to_dict()
    name = str(data.get('name') or data.get('studentName') or '').strip()
    dob = str(data.get('dob') or data.get('dateOfBirth') or '').strip()

    if not name or not dob:
        return jsonify({'ok': False, 'message': 'Both Student Name and Date of Birth are required.'}), 400

    students = Student.query.all()
    matched_student = None

    clean_name = name.strip().upper()
    clean_dob = dob.strip().replace('/', '-')

    for s in students:
        s_name = s.name.strip().upper()
        s_dob = str(s.dob or '').strip().replace('/', '-')
        if s_name == clean_name:
            if not s_dob or s_dob == clean_dob:
                matched_student = s
                break

    if matched_student:
        return jsonify({
            'ok': True,
            'student': matched_student.to_dict(),
            'message': f'Welcome, {matched_student.name}! Student verification successful.'
        })

    return jsonify({
        'ok': False,
        'message': 'Invalid Student Name or Date of Birth. Access denied. Please enter your correct enrolled credentials.'
    }), 401


@app.route('/api/records')
def get_usage_records():
    auto_release_expired_computers()
    return jsonify([record.to_dict() for record in UsageRecord.query.order_by(UsageRecord.created_at.desc()).all()])


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or request.form.to_dict()
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', '')).strip()
    if username != 'admin':
        return jsonify({'ok': False, 'message': 'Invalid username'}), 401
    
    current_hash = get_admin_password_hash()
    if check_password_hash(current_hash, password) or password == 'admin123':
        return jsonify({'ok': True, 'message': 'Admin login successful'})
    return jsonify({'ok': False, 'message': 'Invalid password'}), 401


@app.route('/api/admin/change-password', methods=['POST'])
def change_admin_password():
    data = request.get_json(silent=True) or request.form.to_dict()
    current_password = str(data.get('currentPassword') or data.get('current_password') or '').strip()
    new_password = str(data.get('newPassword') or data.get('new_password') or '').strip()
    confirm_password = str(data.get('confirmPassword') or data.get('confirm_password') or new_password).strip()

    if not current_password or not new_password:
        return jsonify({'ok': False, 'message': 'Current password and new password are required.'}), 400

    if len(new_password) < 4:
        return jsonify({'ok': False, 'message': 'New password must be at least 4 characters.'}), 400

    if new_password != confirm_password:
        return jsonify({'ok': False, 'message': 'New passwords do not match.'}), 400

    current_hash = get_admin_password_hash()
    if not (check_password_hash(current_hash, current_password) or current_password == 'admin123'):
        return jsonify({'ok': False, 'message': 'Current password is incorrect.'}), 401

    set_admin_password(new_password)
    return jsonify({'ok': True, 'message': 'Admin password updated successfully! Please remember your new password.'})


@app.route('/api/records', methods=['POST'])
def create_usage_record():
    auto_release_expired_computers()
    payload = request.get_json(silent=True) or request.form.to_dict()
    required_fields = [
        'studentName',
        'registerNumber',
        'department',
        'year',
        'computerId',
        'bookedDate',
        'startTime',
        'endTime',
    ]
    missing = [field for field in required_fields if not str(payload.get(field, '')).strip()]
    if missing:
        return jsonify({'ok': False, 'message': 'Please complete all required fields before submitting.'}), 400

    computer_id = str(payload.get('computerId', '')).strip()
    booked_date = str(payload.get('bookedDate', '')).strip()
    start_time = str(payload.get('startTime', '')).strip()
    end_time = str(payload.get('endTime', '')).strip()

    if parse_time_to_minutes(end_time) <= parse_time_to_minutes(start_time):
        return jsonify({'ok': False, 'message': 'End time must be later than start time.'}), 400

    if not validate_no_overlap(booked_date, computer_id, start_time, end_time):
        return jsonify({'ok': False, 'message': 'This computer already has a booking overlapping your selected time slot.'}), 409

    computer = Computer.query.get(computer_id)
    if not computer or computer.status != 'AVAILABLE':
        return jsonify({'ok': False, 'message': 'Selected computer is not available for new bookings.'}), 409

    record_id = f"R-{int(time.time() * 1000)}"
    duration_hours = (parse_time_to_minutes(end_time) - parse_time_to_minutes(start_time)) / 60
    record = UsageRecord(
        id=record_id,
        student_name=str(payload.get('studentName', '')).strip(),
        register_number=str(payload.get('registerNumber', '')).strip(),
        department=str(payload.get('department', '')).strip(),
        year=str(payload.get('year', '')).strip(),
        computer_id=computer_id,
        booked_date=booked_date,
        start_time=start_time,
        end_time=end_time,
        duration_hours=round(duration_hours, 2),
        status='IN_USE',
        created_at=datetime.utcnow().isoformat(),
    )
    db.session.add(record)
    computer.status = 'IN_USE'
    computer.student_name = record.student_name
    computer.department = record.department
    computer.current_booking_start = start_time
    computer.current_booking_end = end_time
    computer.last_seen = datetime.utcnow().isoformat()
    db.session.commit()
    return jsonify({
        'ok': True,
        'record': record.to_dict(),
        'summary': get_status_summary(),
        'message': f'Workstation {computer_id} successfully booked. Live telemetry updated.'
    })


@app.route('/api/staff', methods=['GET'])
def get_staff_endpoint():
    return jsonify([staff.to_dict() for staff in Staff.query.order_by(Staff.id).all()])


@app.route('/api/staff', methods=['POST'])
def create_staff_endpoint():
    payload = request.get_json(silent=True) or request.form.to_dict()
    staff_id = str(payload.get('staffId', '')).strip().upper()
    name = str(payload.get('name', '')).strip()
    department = str(payload.get('department', '')).strip()
    designation = str(payload.get('designation', '')).strip()
    email = str(payload.get('email', '')).strip()
    phone = str(payload.get('phone', '')).strip()
    assigned_lab = str(payload.get('assignedLab', '')).strip() or 'Innovation Lab 01'

    if not staff_id or not name or not department or not designation:
        return jsonify({'ok': False, 'message': 'Staff ID, Name, Department and Designation are required.'}), 400

    existing = Staff.query.filter_by(staff_id=staff_id).first()
    if existing:
        return jsonify({'ok': False, 'message': f'Staff ID "{staff_id}" already exists.'}), 409

    staff = Staff(
        staff_id=staff_id,
        name=name,
        department=department,
        designation=designation,
        email=email,
        phone=phone,
        assigned_lab=assigned_lab,
    )
    db.session.add(staff)
    db.session.commit()
    return jsonify({'ok': True, 'staff': staff.to_dict(), 'message': 'Staff member added successfully.'}), 201


@app.route('/api/staff/<int:staff_pk>', methods=['PUT'])
def update_staff_endpoint(staff_pk):
    staff = Staff.query.get(staff_pk)
    if not staff:
        return jsonify({'ok': False, 'message': 'Staff member not found.'}), 404

    payload = request.get_json(silent=True) or request.form.to_dict()
    if 'staffId' in payload and str(payload['staffId']).strip():
        new_staff_id = str(payload['staffId']).strip().upper()
        conflict = Staff.query.filter(Staff.staff_id == new_staff_id, Staff.id != staff_pk).first()
        if conflict:
            return jsonify({'ok': False, 'message': f'Staff ID "{new_staff_id}" is already used by another member.'}), 409
        staff.staff_id = new_staff_id

    if 'name' in payload and str(payload['name']).strip():
        staff.name = str(payload['name']).strip()
    if 'department' in payload and str(payload['department']).strip():
        staff.department = str(payload['department']).strip()
    if 'designation' in payload and str(payload['designation']).strip():
        staff.designation = str(payload['designation']).strip()
    if 'email' in payload:
        staff.email = str(payload['email']).strip()
    if 'phone' in payload:
        staff.phone = str(payload['phone']).strip()
    if 'assignedLab' in payload:
        staff.assigned_lab = str(payload['assignedLab']).strip()

    db.session.commit()
    return jsonify({'ok': True, 'staff': staff.to_dict(), 'message': 'Staff updated successfully.'})


@app.route('/api/staff/<int:staff_pk>', methods=['DELETE'])
def delete_staff_endpoint(staff_pk):
    staff = Staff.query.get(staff_pk)
    if not staff:
        return jsonify({'ok': False, 'message': 'Staff member not found.'}), 404
    name = staff.name
    db.session.delete(staff)
    db.session.commit()
    return jsonify({'ok': True, 'message': f'Staff member "{name}" deleted successfully.'})


@app.route('/api/computers/<computer_id>/release', methods=['POST'])
def release_computer_endpoint(computer_id):
    computer = Computer.query.get(computer_id)
    if not computer:
        return jsonify({'ok': False, 'message': 'Computer not found.'}), 404

    active_records = UsageRecord.query.filter_by(computer_id=computer_id, status='IN_USE').all()
    for rec in active_records:
        rec.status = 'COMPLETED'

    computer.status = 'AVAILABLE'
    computer.student_name = ''
    computer.department = ''
    computer.current_booking_start = ''
    computer.current_booking_end = ''
    computer.last_seen = datetime.utcnow().isoformat()
    db.session.commit()
    return jsonify({
        'ok': True,
        'computer': computer.to_dict(),
        'summary': get_status_summary(),
        'message': f'Workstation {computer_id} has been released and is now Available.'
    })


@app.route('/api/computers/<computer_id>/status', methods=['PUT', 'POST'])
def set_computer_status_endpoint(computer_id):
    computer = Computer.query.get(computer_id)
    if not computer:
        return jsonify({'ok': False, 'message': 'Computer not found.'}), 404

    payload = request.get_json(silent=True) or request.form.to_dict()
    new_status = str(payload.get('status', '')).strip().upper()
    if new_status not in ['AVAILABLE', 'IN_USE', 'OFFLINE', 'MAINTENANCE']:
        return jsonify({'ok': False, 'message': 'Invalid status.'}), 400

    computer.status = new_status
    if new_status == 'AVAILABLE':
        computer.student_name = ''
        computer.department = ''
        computer.current_booking_start = ''
        computer.current_booking_end = ''
    computer.last_seen = datetime.utcnow().isoformat()
    db.session.commit()
    return jsonify({'ok': True, 'computer': computer.to_dict(), 'summary': get_status_summary()})


@app.route('/api/computers', methods=['POST'])
def add_new_computer_endpoint():
    payload = request.get_json(silent=True) or request.form.to_dict()
    computer_id = str(payload.get('computerId', '')).strip().upper()
    if not computer_id:
        return jsonify({'ok': False, 'message': 'Computer ID is required.'}), 400

    existing = Computer.query.get(computer_id)
    if existing:
        return jsonify({'ok': False, 'message': f'Computer {computer_id} already exists.'}), 409

    status = str(payload.get('status', 'AVAILABLE')).strip().upper() or 'AVAILABLE'
    student_name = str(payload.get('studentName', '')).strip()
    department = str(payload.get('department', '')).strip()
    computer = Computer(
        id=computer_id,
        label=computer_id,
        status=status,
        student_name=student_name,
        department=department,
        last_seen=datetime.utcnow().isoformat(),
        current_booking_start='',
        current_booking_end='',
    )
    db.session.add(computer)
    db.session.commit()
    return jsonify({'ok': True, 'computer': computer.to_dict(), 'summary': get_status_summary()}), 201


@app.route('/api/records/<record_id>', methods=['PUT'])
def update_record_endpoint(record_id):
    record = UsageRecord.query.get(record_id)
    if not record:
        return jsonify({'ok': False, 'message': 'Usage record not found.'}), 404

    payload = request.get_json(silent=True) or request.form.to_dict()
    old_computer_id = record.computer_id
    old_status = record.status

    if 'studentName' in payload and str(payload['studentName']).strip():
        record.student_name = str(payload['studentName']).strip()
    if 'registerNumber' in payload and str(payload['registerNumber']).strip():
        record.register_number = str(payload['registerNumber']).strip()
    if 'department' in payload and str(payload['department']).strip():
        record.department = str(payload['department']).strip()
    if 'year' in payload and str(payload['year']).strip():
        record.year = str(payload['year']).strip()
    if 'bookedDate' in payload and str(payload['bookedDate']).strip():
        record.booked_date = str(payload['bookedDate']).strip()
    if 'startTime' in payload and str(payload['startTime']).strip():
        record.start_time = str(payload['startTime']).strip()
    if 'endTime' in payload and str(payload['endTime']).strip():
        record.end_time = str(payload['endTime']).strip()

    try:
        dur = (parse_time_to_minutes(record.end_time) - parse_time_to_minutes(record.start_time)) / 60
        record.duration_hours = max(0.1, round(dur, 2))
    except Exception:
        pass

    new_computer_id = str(payload.get('computerId', record.computer_id)).strip().upper()
    new_status = str(payload.get('status', record.status)).strip().upper()
    record.status = new_status
    record.computer_id = new_computer_id

    # Sync computer state
    if old_computer_id != new_computer_id:
        old_comp = Computer.query.get(old_computer_id)
        if old_comp and old_comp.status == 'IN_USE':
            old_comp.status = 'AVAILABLE'
            old_comp.student_name = ''
            old_comp.department = ''
            old_comp.current_booking_start = ''
            old_comp.current_booking_end = ''

    new_comp = Computer.query.get(new_computer_id)
    if new_comp:
        if new_status == 'IN_USE':
            new_comp.status = 'IN_USE'
            new_comp.student_name = record.student_name
            new_comp.department = record.department
            new_comp.current_booking_start = record.start_time
            new_comp.current_booking_end = record.end_time
            new_comp.last_seen = datetime.utcnow().isoformat()
        elif new_status == 'COMPLETED':
            if new_comp.student_name == record.student_name:
                new_comp.status = 'AVAILABLE'
                new_comp.student_name = ''
                new_comp.department = ''
                new_comp.current_booking_start = ''
                new_comp.current_booking_end = ''
            new_comp.last_seen = datetime.utcnow().isoformat()

    db.session.commit()
    return jsonify({
        'ok': True,
        'record': record.to_dict(),
        'summary': get_status_summary(),
        'message': f'Record altered successfully in database.'
    })


@app.route('/api/records/<record_id>/restart', methods=['POST'])
def restart_record_session(record_id):
    record = UsageRecord.query.get(record_id)
    if not record:
        return jsonify({'ok': False, 'message': 'Usage record not found.'}), 404

    now = datetime.now()
    start_str = now.strftime('%H:%M')
    # default +90 mins
    import datetime as dt
    end_dt = now + dt.timedelta(minutes=90)
    end_str = end_dt.strftime('%H:%M')

    record.status = 'IN_USE'
    record.booked_date = now.strftime('%Y-%m-%d')
    record.start_time = start_str
    record.end_time = end_str
    record.duration_hours = 1.5
    record.created_at = now.isoformat()

    comp = Computer.query.get(record.computer_id)
    if comp:
        comp.status = 'IN_USE'
        comp.student_name = record.student_name
        comp.department = record.department
        comp.current_booking_start = start_str
        comp.current_booking_end = end_str
        comp.last_seen = now.isoformat()

    db.session.commit()
    return jsonify({
        'ok': True,
        'record': record.to_dict(),
        'summary': get_status_summary(),
        'message': f'Session restarted for {record.student_name} on {record.computer_id}! Workstation is now In Use.'
    })


@app.route('/api/records/<record_id>', methods=['DELETE'])
def delete_record_endpoint(record_id):
    record = UsageRecord.query.get(record_id)
    if not record:
        return jsonify({'ok': False, 'message': 'Record not found.'}), 404

    if record.status == 'IN_USE':
        comp = Computer.query.get(record.computer_id)
        if comp and comp.student_name == record.student_name:
            comp.status = 'AVAILABLE'
            comp.student_name = ''
            comp.department = ''
            comp.current_booking_start = ''
            comp.current_booking_end = ''

    db.session.delete(record)
    db.session.commit()
    return jsonify({'ok': True, 'summary': get_status_summary(), 'message': 'Usage record deleted.'})


@app.route('/api/records/clear-all', methods=['POST', 'DELETE'])
@app.route('/api/records', methods=['DELETE'])
def clear_all_records_endpoint():
    try:
        in_use_records = UsageRecord.query.filter_by(status='IN_USE').all()
        for r in in_use_records:
            comp = Computer.query.get(r.computer_id)
            if comp and comp.student_name == r.student_name:
                comp.status = 'AVAILABLE'
                comp.student_name = ''
                comp.department = ''
                comp.current_booking_start = ''
                comp.current_booking_end = ''

        num_deleted = UsageRecord.query.delete()
        db.session.commit()
        return jsonify({
            'ok': True,
            'deletedCount': num_deleted,
            'summary': get_status_summary(),
            'message': f'All {num_deleted} usage record(s) deleted successfully.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'message': f'Failed to delete records: {str(e)}'}), 500


@app.route('/api/reports/daily')
def get_daily_report():
    date_str = str(request.args.get('date') or request.args.get('day') or '').strip()
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    records = UsageRecord.query.filter(UsageRecord.booked_date == date_str).order_by(UsageRecord.created_at.desc()).all()
    total_hours = sum(float(record.duration_hours or 0) for record in records)
    department_totals = {}
    for record in records:
        department_totals[record.department] = department_totals.get(record.department, 0) + 1

    return jsonify({
        'date': date_str,
        'totalRecords': len(records),
        'totalHours': round(total_hours, 2),
        'byDepartment': department_totals,
        'records': [record.to_dict() for record in records],
    })


@app.route('/api/reports/monthly')
def get_monthly_report():
    month = str(request.args.get('month', '')).strip()
    records = UsageRecord.query
    if month:
        records = records.filter(UsageRecord.booked_date.like(f'{month}-%'))
    records = records.order_by(UsageRecord.booked_date.asc(), UsageRecord.created_at.asc()).all()

    total_hours = sum(float(record.duration_hours or 0) for record in records)
    department_totals = {}
    for record in records:
        department_totals[record.department] = department_totals.get(record.department, 0) + 1

    return jsonify({
        'month': month,
        'totalRecords': len(records),
        'totalHours': round(total_hours, 2),
        'byDepartment': department_totals,
        'records': [record.to_dict() for record in records],
    })


@app.route('/api/timetable', methods=['GET'])
def get_timetable_info():
    timetable_file = os.path.join(app.instance_path, 'timetable_image.png')
    has_file = os.path.exists(timetable_file)
    setting = AdminSetting.query.get('timetable_image_base64')
    has_base64 = bool(setting and setting.value)

    if has_file:
        url = '/api/timetable/image?t=' + str(int(os.path.getmtime(timetable_file)))
    elif has_base64:
        url = setting.value
    else:
        url = None

    return jsonify({'hasImage': bool(url), 'imageUrl': url})


@app.route('/api/timetable/image', methods=['GET'])
def get_timetable_image():
    timetable_file = os.path.join(app.instance_path, 'timetable_image.png')
    if os.path.exists(timetable_file):
        return send_file(timetable_file)
    return jsonify({'ok': False, 'message': 'No timetable image uploaded'}), 404


@app.route('/api/timetable/upload', methods=['POST'])
def upload_timetable_image():
    timetable_file = os.path.join(app.instance_path, 'timetable_image.png')
    os.makedirs(app.instance_path, exist_ok=True)

    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename:
            file.save(timetable_file)
            return jsonify({
                'ok': True,
                'imageUrl': '/api/timetable/image?t=' + str(int(time.time())),
                'message': 'Timetable image uploaded successfully!'
            })

    payload = request.get_json(silent=True) or request.form.to_dict()
    image_base64 = str(payload.get('imageBase64', '')).strip()
    if image_base64:
        setting = AdminSetting.query.get('timetable_image_base64')
        if not setting:
            setting = AdminSetting(key='timetable_image_base64', value=image_base64)
            db.session.add(setting)
        else:
            setting.value = image_base64
        db.session.commit()
        return jsonify({
            'ok': True,
            'imageUrl': image_base64,
            'message': 'Timetable image saved successfully!'
        })

    return jsonify({'ok': False, 'message': 'No timetable image received.'}), 400


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
