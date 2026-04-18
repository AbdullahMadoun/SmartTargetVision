from DroneController import DroneController
from PersonTracker import PersonTracker

def main():
    print("[MAIN] Initializing Flight Controller Connection...")
    #drone = DroneController(connection_string = 'udp:172.25.48.1:14551', baud_rate = 115200) #Use when simulating
    drone = DroneController(connection_string='/dev/ttyTHS1', baud_rate=921600) #Use when on jetson
    mode = drone.get_current_mode(blocking=True, timeout=1.0)
    armed = drone.is_armed()
    print(f"[MAIN] Flight state detected: mode={mode or 'UNKNOWN'}, armed={armed}")
    print("[MAIN] Vision will stay idle until the drone is manually put in GUIDED and armed from the ground station.")

    print("[MAIN] Initializing Vision Tracker...")
    tracker = PersonTracker(drone=drone, engine_path='yolo_trt.engine', camera_index=0) #camera idx normally zero for jetson nano usb cam
    print("[MAIN] Starting Tracking Loop...")
    tracker.tracking_loop()

main()

