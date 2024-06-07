from flask import Flask, render_template , request
from detection import AccidentDetectionModel
from flask_socketio import SocketIO
from twilio.rest import Client
from threading import Lock
import numpy as np
import base64
import json
import time
import cv2
import os
import io

app = Flask(__name__)
model = AccidentDetectionModel("model.json", 'model_weights.h5')
font = cv2.FONT_HERSHEY_SIMPLEX
thread = None
thread_lock = Lock()
app.config['SECRET_KEY'] = 'qers'
socketio = SocketIO(app, cors_allowed_origins='*')
account_sid = "AC8b7ec6b22f20f9e43ddbb47db6022266"
auth_token = "ef5abfd5d95c2cd7cfb5e7e0274f5d70"
client = Client(account_sid, auth_token)
last_call_time = 0

with open('config.json') as f:
    configData = json.load(f)
    stream_on = configData.get('stream_on')
    id = configData.get('id')
    address = configData.get('address')
    location_lat = configData.get('location').get('lat')
    location_lon = configData.get('location').get('lon')
    owner_info_phno = configData.get('owner_info').get('phno')
    owner_info_email = configData.get('owner_info').get('email')
    emergency_contact_phno = configData.get('emergency-contact').get('phno')
    emergency_contact_email = configData.get('emergency-contact').get('email')
    emergency_contact_address = configData.get('emergency-contact').get('address')
    
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/config")
def config():
    return render_template("config.html")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(502)
def bad_gateway(e):
    return render_template('502.html'), 502

@app.errorhandler(503)
def server_maintenance(e):
    return '''
        <html>
            <head>
                <title>Maintenance Mode</title>
            </head>
            <body>
                <h1>Maintenance Mode</h1>
                <p>The server is currently undergoing maintenance. Please try again later.</p>
            </body>
        </html>
    ''', 503

@socketio.on('connect')
def connect():
    global thread
    print('Client connected')
    with thread_lock:
        if thread is None:
            print("Starting background task")
            thread = socketio.start_background_task(readData, stream_on)
            print("Background task started")

def readData(streamUrl):
    print("readData function started")
    video = cv2.VideoCapture(streamUrl)
    frame_buffer = []
    start_time = time.time()

    while True:
        ret, frame = video.read()
        print("Frame read:", ret)
        frame_buffer.append(frame)

        if time.time() - start_time >= 0.5:  # 1 second buffer
            process_buffer(frame_buffer)
            frame_buffer = []
            start_time = time.time()

def process_buffer(frames):
    global last_call_time
    for frame in frames:
        if frame is not None:
            isOngoing = True
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            roi = cv2.resize(gray_frame, (250, 250))

            pred, prob = model.predict_accident(roi[np.newaxis, :, :])
            print("Prediction:", pred, prob)
            if(pred == "Accident"):
                prob = (round(prob[0][0]*100, 2))
                if(prob > 50):
                        current_time = time.time()
                        if current_time - last_call_time > 900:  # 900 seconds = 15 minutes
                            call = client.calls.create(
                                twiml=f'''
                                    <Response>
                                        <Say voice="man">
                                            This is a call from Q.E.R.S , 
                                            We detected an accident near {address}% , Please try to reach as soon as possible.
                                            Further detail of the accident will share to you by email. Please Check it out.
                                            <Pause length="1"/>
                                            I Repeat,
                                            <Pause length="1"/>
                                            We detected an accident near {address}% , Please try to reach as soon as possible.
                                            <Pause length="2"/>
                                            Thank You                                 
                                        </Say>
                                    </Response>
                                ''',
                                to= emergency_contact_phno,
                                from_="+12406479238"
                            )
                            last_call_time = current_time
        else:
            print("Session ended")
            isOngoing = False
            socketio.emit('data', {'frame': None,'result': None , 'ongoing' : isOngoing})
            break
        _, frame_encode = cv2.imencode('.jpg', frame)
        frame_base64 = base64.b64encode(frame_encode).decode('utf-8')
        print("Emitting data to client")
        socketio.emit('data', {'frame': frame_base64,'result': str(prob) , 'ongoing' : isOngoing})

if __name__ == "__main__":
    socketio.run(app)