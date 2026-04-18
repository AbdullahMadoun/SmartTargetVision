import cv2
import numpy as np
from ultralytics import YOLO
import os
import time

class PersonTracker:
    def __init__(self, drone, model_path, camera_index):  #cam idx might be different

        print(f"[PersonTracker] Loading YOLO from: {model_path}...")
        self.model = YOLO(model_path)
        self.target_id = None
        self.drone = drone
        
        os_env = os.getenv('OS_ENV', 'jetson').lower()
        if os_env == 'windows':
            self.cap = cv2.VideoCapture(2, cv2.CAP_DSHOW) #FOR WINDOWS
        else:
            self.cap = cv2.VideoCapture(camera_index) #FOR JETSON NANO
        
        if not self.cap.isOpened():
            raise Exception("[PersonTracker] ***Error: Camera Loading Error***")
        
        # get the camera resolution
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[PersonTracker] Camera initialized @ resolution: {self.frame_width}x{self.frame_height}")

        #***Adjust Parameters***
        self.target_ideal_area = int(os.getenv('TARGET_IDEAL_AREA', '50000'))           # Smaller value = higher drone altitude, larger value = lower
        self.vertical_deadzone = int(os.getenv('VERTICAL_DEADZONE', '5000'))            # Tolerance
        self.horizontal_deadzone_radius = int(os.getenv('HORIZONTAL_DEADZONE', '25'))   # deadzone in pixels for horizontal movements

        self.is_visdrone = (os.getenv('MODEL_TYPE', 'std').lower() == 'visdrone')
        self.allowed_modes = {'GUIDED'}
        self._last_gate_check = 0.0
        self._tracking_enabled = False
        self._last_gate_state = None

    def tracking_loop(self):
        # Main loop to capture video frames and perform detection.
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    print("[PersonTracker] **Error: Failed to grab frame.***")
                    break

                tracking_allowed = self._tracking_authorized()
                tracking_active = False

                if tracking_allowed:
                    if self.is_visdrone:
                        results = self.model.track(frame, classes=[0, 1], conf=0.30, persist=True, verbose=False)
                    else:
                        results = self.model.track(frame, classes=[0], conf=0.5, persist=True, verbose=False)

                    if len(results[0].boxes) > 0 and results[0].boxes.id is not None:
                        boxes = results[0].boxes.xyxy.cpu().numpy()         #grab bounding boxes
                        ids = results[0].boxes.id.cpu().numpy().astype(int) #grab ids for detections
                        if self.target_id is None or self.target_id not in ids: #if theres no target currently selected
                            self.target_id = ids[0]                             #select first detection in current frame as target
                            print(f"Target switched to ID: {self.target_id}")

                        if self.target_id in ids:                   #if target in current frame
                            idx = list(ids).index(self.target_id)   #grab index of target
                            x1, y1, x2, y2 = map(int, boxes[idx])   #grab coords for target

                            speeds, measurements = self._calculate_velocities(x1, y1, x2, y2)
                            self.drone.send_velocity_cmd(*speeds)
                            self._draw_hud(frame, x1, y1, x2, y2, measurements)

                            tracking_active = True

                if not tracking_active:     #if no target found
                    self.target_id = None   #reset target
                    status_text = "SEARCHING FOR TARGET..."
                    status_color = (0, 0, 255)
                    if not tracking_allowed:
                        status_text = "WAITING FOR MANUAL TAKEOFF (GUIDED + ARMED)..."
                        status_color = (0, 255, 255)

                    cv2.putText(frame, status_text, (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
                    if tracking_allowed:
                        self.drone.send_velocity_cmd(0,0,0,0)   #No target, maintain position
                        
                # Display cam feed
                cv2.imshow("ONNX Vision Tracker", frame)

                # exit with q (cam feed frame should be in focus)
                if cv2.waitKey(1) == ord('q'):
                    break
        finally:
            self.cap.release()
            cv2.destroyAllWindows()

    def _tracking_authorized(self):
        now = time.monotonic()
        if now - self._last_gate_check >= 0.5:
            mode, armed = self.drone.refresh_flight_state(timeout=0.0)
            self._tracking_enabled = armed and mode in self.allowed_modes

            gate_state = (mode, armed, self._tracking_enabled)
            if gate_state != self._last_gate_state:
                mode_name = mode or "UNKNOWN"
                if self._tracking_enabled:
                    print(f"[PersonTracker] Tracking enabled. Mode={mode_name}, armed={armed}")
                else:
                    print(f"[PersonTracker] Tracking paused. Mode={mode_name}, armed={armed}")
                self._last_gate_state = gate_state

            self._last_gate_check = now

        return self._tracking_enabled

    # Helper Functions
    def _calculate_velocities(self, x1, y1, x2, y2):
        frame_center_x = self.frame_width // 2
        frame_center_y = self.frame_height // 2
        target_center_x = (x1 + x2) // 2
        target_center_y = (y1 + y2) // 2
        target_area = (x2 - x1) * (y2 - y1)
        offset_x = target_center_x - frame_center_x
        offset_y = target_center_y - frame_center_y
        distance_from_center = np.sqrt(offset_x**2 + offset_y**2)

        if distance_from_center > self.horizontal_deadzone_radius:
            # forward/backward velocity (x) of drone maps to vertical screen offset
            forward_speed = -0.002 * offset_y   #Down on screen is +ve
            # left/right velocity (y) maps to horizontal screen offset
            right_speed = 0.002 * offset_x      #Right on screen is +ve
        else:
            #dont move
            forward_speed = 0
            right_speed = 0

        vertical_speed = 0
        if os.getenv('VERTICAL_VELOCITY','false').lower() == 'true':
            area_diff = self.target_ideal_area - target_area
            if abs(area_diff) > self.vertical_deadzone:
                vertical_speed = 0.00002 * area_diff

        yaw_rate = 0

        if os.getenv('SPEED_SAFETY', 'false').lower() == 'true':
            forward_speed = np.clip(forward_speed, -1, 1)         #clip the speed to 1m/s max for safety
            right_speed = np.clip(right_speed, -1, 1)             #clip the speed to 1m/s max for safety
            vertical_speed = np.clip(vertical_speed, -0.5, 0.5)   #clip the speed to 0.5m/s max for safety

        speeds = (forward_speed, right_speed, vertical_speed, yaw_rate)
        measurements = (offset_x, offset_y, target_area, target_center_x, target_center_y)

        return speeds, measurements

    def _draw_hud(self, frame, x1, y1, x2, y2, measurements):
        offset_x, offset_y, target_area, target_center_x, target_center_y = measurements
        frame_center_x = self.frame_width //2
        frame_center_y = self.frame_height //2

        # Draw center lines
        cv2.line(frame, (frame_center_x, 0), (frame_center_x, self.frame_height), (255, 255, 255), 1)
        cv2.line(frame, (0, frame_center_y), (self.frame_width, frame_center_y), (200, 200, 200), 1)

        # Draw Horizontal Deadzone circle
        cv2.circle(frame, (frame_center_x, frame_center_y), self.horizontal_deadzone_radius, (255, 255, 0), 2)
        
        #Draw Bounding Box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
        
        #Add details to bounding box
        cv2.putText(frame, f"DX: {offset_x} | DY: {offset_y} | Area: {target_area}", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        cv2.circle(frame, (target_center_x, target_center_y), 5, (0, 255, 0), -1)

# tracker = PersonTracker(model_path='yolov8n.onnx', camera_index=0)
# tracker.tracking_loop()
