from flask import Flask, request, render_template, redirect, url_for, flash
import spotipy
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Replace these with your Spotify app credentials
CLIENT_ID = '4d53388937344ce18e391158682e90bc'
CLIENT_SECRET = 'e98daeb1aaeb451ab7abcb53d8e69a64'
REDIRECT_URI = 'http://localhost:8888/callback'

# Scope for accessing user's playback state and controlling playback
SCOPE = 'user-read-playback-state user-modify-playback-state'

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                               client_secret=CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope=SCOPE))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    track_name = request.form['track_name']
    global tracks
    tracks = search_track(track_name)
    
    if tracks:
        return render_template('index.html', tracks=tracks)
    else:
        flash("No tracks found.")
        return redirect(url_for('index'))

@app.route('/authorize', methods=['POST'])
def authorize():
    track_index = int(request.form['track_index'])
    selected_track = tracks[track_index]
    add_track_to_queue(selected_track['uri'])
    flash(f"Adding {selected_track['name']} by {', '.join(artist['name'] for artist in selected_track['artists'])} to the queue.")
    return redirect(url_for('index'))

@app.route('/devices')
def list_devices():
    devices = sp.devices()
    if devices['devices']:
        return render_template('index.html', devices=devices['devices'])
    else:
        flash("No Spotify devices found. Please start a device and try again.")
        return redirect(url_for('index'))

def search_track(track_name):
    results = sp.search(q=track_name, limit=10, type='track')
    return results['tracks']['items']

def add_track_to_queue(track_uri):
    devices = sp.devices()
    if devices['devices']:
        selected_device_id = request.form['device_id']
        sp.transfer_playback(device_id=selected_device_id, force_play=True)
        sp.add_to_queue(track_uri)
    else:
        flash("No active Spotify device found. Please start playing music on a device and try again.")

if __name__ == '__main__':
    app.run(debug=True)
