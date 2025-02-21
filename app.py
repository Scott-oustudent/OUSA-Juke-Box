from flask import Flask, request, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Flask-Login configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Replace these with your Spotify app credentials
CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID', '4d53388937344ce18e391158682e90bc')
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET', 'e98daeb1aaeb451ab7abcb53d8e69a64')
REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://localhost:8888/callback')

# Scope for accessing user's playback state and controlling playback
SCOPE = 'user-read-playback-state user-modify-playback-state'

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                               client_secret=CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope=SCOPE))

# Global lists to store requested tracks and request history
requested_tracks = []
request_history = []
tracks = []  # Define the global variable tracks

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='user')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    return render_template('index.html', request_history=request_history)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            if check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('Invalid password')
        else:
            flash('Invalid username')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = 'user'
        if username == 'scott.harveywhittle@ou.ac.uk':
            role = 'administrator'
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(username=username, password=hashed_password, role=role)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        user = User.query.filter_by(username=username).first()
        if user:
            new_password = 'defaultpassword'  # You can generate a random password here
            user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
            db.session.commit()
            flash(f'Password for {user.username} has been reset to the default password.')
            return redirect(url_for('login'))
        else:
            flash('Username not found')
    return render_template('forgot_password.html')

@app.route('/search', methods=['POST'])
@login_required
def search():
    track_name = request.form['track_name']
    if not track_name:
        flash("Please enter a track name.")
        return redirect(url_for('index'))

    global tracks
    tracks = search_track(track_name)

    if tracks:
        return render_template('index.html', tracks=tracks, request_history=request_history)
    else:
        flash("No tracks found.")
        return redirect(url_for('index'))

@app.route('/request_track', methods=['POST'])
@login_required
def request_track():
    track_index = int(request.form['track_index'])
    selected_track = tracks[track_index]
    requested_tracks.append(selected_track)
    request_history.append({'track': selected_track, 'status': 'Requested'})
    flash(f"Track requested: {selected_track['name']} by {', '.join(artist['name'] for artist in selected_track['artists'])}")
    return redirect(url_for('index'))

@app.route('/manager')
@login_required
def manager():
    if current_user.role not in ['administrator', 'music_manager']:
        flash('Access denied')
        return redirect(url_for('index'))
    return render_template('manager.html', tracks=requested_tracks, request_history=request_history)

@app.route('/authorize', methods=['POST'])
@login_required
def authorize():
    if current_user.role not in ['administrator', 'music_manager']:
        flash('Access denied')
        return redirect(url_for('index'))
    track_index = int(request.form['track_index'])
    selected_track = requested_tracks.pop(track_index)
    device_id = request.form.get('device_id')
    if device_id:
        add_track_to_queue(selected_track['uri'], device_id)
        for req in request_history:
            if req['track']['uri'] == selected_track['uri']:
                req['status'] = 'Authorized'
        flash(f"Adding {selected_track['name']} by {', '.join(artist['name'] for artist in selected_track['artists'])} to the queue.")
    else:
        flash("No device selected.")
    return redirect(url_for('manager'))

@app.route('/devices')
@login_required
def list_devices():
    if current_user.role not in ['administrator', 'music_manager']:
        flash('Access denied')
        return redirect(url_for('index'))
    devices = sp.devices()
    if devices['devices']:
        return render_template('manager.html', devices=devices['devices'], tracks=requested_tracks, request_history=request_history)
    else:
        flash("No Spotify devices found. Please start a device and try again.")
        return redirect(url_for('manager'))

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'administrator':
        flash('Access denied')
        return redirect(url_for('index'))
    users = User.query.all()
    return render_template('admin.html', users=users)

@app.route('/update_role', methods=['POST'])
@login_required
def update_role():
    if current_user.role != 'administrator':
        flash('Access denied')
        return redirect(url_for('index'))
    user_id = request.form['user_id']
    new_role = request.form['role']
    user = User.query.get(user_id)
    if user:
        user.role = new_role
        db.session.commit()
        flash('User role updated successfully')
    else:
        flash('User not found')
    return redirect(url_for('admin'))

@app.route('/reset_password', methods=['POST'])
@login_required
def reset_password():
    if current_user.role != 'administrator':
        flash('Access denied')
        return redirect(url_for('index'))
    user_id = request.form['user_id']
    user = User.query.get(user_id)
    if user:
        new_password = 'defaultpassword'  # You can generate a random password here
        user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        flash(f'Password for {user.username} has been reset to the default password.')
    else:
        flash('User not found')
    return redirect(url_for('admin'))

def search_track(track_name):
    results = sp.search(q=track_name, limit=10, type='track')
    return results['tracks']['items']

def add_track_to_queue(track_uri, device_id):
    sp.transfer_playback(device_id=device_id, force_play=True)
    sp.add_to_queue(track_uri)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Add zx810530@open.ac.uk as administrator by default
        if not User.query.filter_by(username='zx810530@open.ac.uk').first():
            admin_user = User(username='zx810530@open.ac.uk', password=generate_password_hash('defaultpassword', method='pbkdf2:sha256'), role='administrator')
            db.session.add(admin_user)
            db.session.commit()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

