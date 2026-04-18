import os
from DroneController import DroneController
from PersonTracker import PersonTracker

def main():
    conn_string = os.getenv('CONNECTION_STRING', '/dev/ttyTHS1')
    baud_rate = int(os.getenv('BAUD_RATE', '921600'))
    cam_index = int(os.getenv('CAM_INDEX', '0'))
    model_type = os.getenv('MODEL_TYPE', 'std').lower()

    if model_type == 'visdrone':
        model_path = 'yolov8n_visdrone.engine'
    else:
        model_path = 'yolov8n.engine'

    print("[MAIN] Initializing Flight Controller Connection...")
    drone = DroneController(connection_string = conn_string, baud_rate = baud_rate)
    mode = drone.get_current_mode(blocking=True, timeout=1.0)
    armed = drone.is_armed()
    print(f"[MAIN] Flight state detected: mode={mode or 'UNKNOWN'}, armed={armed}")
    print("[MAIN] Vision will stay idle until the drone is manually put in GUIDED and armed from the ground station.")

    print("[MAIN] Initializing Vision Tracker...")
    tracker = PersonTracker(drone=drone, model_path=model_path, camera_index=cam_index) #camera idx normally zero for jetson nano usb cam
    print("[MAIN] Starting Tracking Loop...")
    tracker.tracking_loop()

main()

