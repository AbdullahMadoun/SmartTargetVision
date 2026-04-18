import cv2
import numpy as np
import time

#  REMOVED: ultralytics
# from ultralytics import YOLO

#  CHANGED: TensorRT + PyCUDA imports
import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit


class PersonTracker:
    def __init__(self, drone, engine_path, camera_index):

        print(f"[PersonTracker] Loading TensorRT engine from: {engine_path}...")

        self.drone = drone
        self.target_id = None

        #  CHANGED: Load TensorRT engine
        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as f:
            runtime = trt.Runtime(logger)
            self.engine = runtime.deserialize_cuda_engine(f.read())

        self.context = self.engine.create_execution_context()

        #  CHANGED: Allocate buffers
        self.inputs = []
        self.outputs = []
        self.bindings = []
        self.stream = cuda.Stream()

        for binding in self.engine:
            shape = self.engine.get_binding_shape(binding)
            size = trt.volume(shape)
            dtype = trt.nptype(self.engine.get_binding_dtype(binding))

            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)

            self.bindings.append(int(device_mem))

            if self.engine.binding_is_input(binding):
                self.inputs.append((host_mem, device_mem))
            else:
                self.outputs.append((host_mem, device_mem))

        #  CHANGED: Camera fix (Jetson)
        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            raise Exception("[PersonTracker] ***Error: Camera Loading Error***")

        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[PersonTracker] Camera initialized @ resolution: {self.frame_width}x{self.frame_height}")

        # Parameters (unchanged)
        self.target_ideal_area = 50000
        self.vertical_deadzone = 5000
        self.horizontal_deadzone_radius = 25
        self.allowed_modes = {'GUIDED'}
        self._last_gate_check = 0.0
        self._tracking_enabled = False
        self._last_gate_state = None

    def tracking_loop(self):
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    print("[PersonTracker] **Error: Failed to grab frame.***")
                    break

                tracking_allowed = self._tracking_authorized()
                tracking_active = False

                if tracking_allowed:
                    # CHANGED: TensorRT inference
                    detections = self._run_inference(frame)

                    if len(detections) > 0:
                        # pick first detection (like your old code)
                        x1, y1, x2, y2, conf = detections[0]

                        speeds, measurements = self._calculate_velocities(x1, y1, x2, y2)

                        #  SAFETY: you can comment this during testing
                        self.drone.send_velocity_cmd(*speeds)

                        self._draw_hud(frame, x1, y1, x2, y2, measurements)
                        tracking_active = True

                if not tracking_active:
                    self.target_id = None
                    status_text = "SEARCHING FOR TARGET..."
                    status_color = (0, 0, 255)
                    if not tracking_allowed:
                        status_text = "WAITING FOR MANUAL TAKEOFF (GUIDED + ARMED)..."
                        status_color = (0, 255, 255)

                    cv2.putText(frame, status_text, (20, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
                    if tracking_allowed:
                        self.drone.send_velocity_cmd(0, 0, 0, 0)

                cv2.imshow("TensorRT Vision Tracker", frame)

                if cv2.waitKey(1) == ord('q'):
                    break

        finally:
            self.cap.release()
            cv2.destroyAllWindows()

    def _tracking_authorized(self):
        now = time.monotonic()
        if now - self._last_gate_check >= 0.5:
            mode, armed = self.drone.refresh_flight_state(blocking=True, timeout=1.5)
            self._tracking_enabled = armed

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

    #  NEW: TensorRT inference function
    def _run_inference(self, frame):
        orig_h, orig_w = frame.shape[:2]

        img = cv2.resize(frame, (640, 640))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        np.copyto(self.inputs[0][0], img.ravel())

        cuda.memcpy_htod_async(self.inputs[0][1], self.inputs[0][0], self.stream)

        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)

        cuda.memcpy_dtoh_async(self.outputs[0][0], self.outputs[0][1], self.stream)
        self.stream.synchronize()

        #  CHANGED: reshape dynamically
        output = self.outputs[0][0]
        num_channels = output.size // 8400
        output = output.reshape(1, num_channels, 8400)

        return self._decode(output, orig_w, orig_h)

    #  NEW: decode YOLOv8 output
    def _decode(self, output, orig_w, orig_h, conf_thresh=0.5):
        output = output[0]

        boxes = output[:4, :]
        scores = output[4:, :]

        class_ids = np.argmax(scores, axis=0)
        confidences = np.max(scores, axis=0)

        # class 0 = person (adjust if using VisDrone)
        mask = (class_ids == 0) & (confidences > conf_thresh)

        boxes = boxes[:, mask]
        confidences = confidences[mask]

        if boxes.shape[1] == 0:
            return []

        boxes = boxes.T

        cx, cy, bw, bh = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]

        x1 = (cx - bw / 2) * orig_w / 640
        y1 = (cy - bh / 2) * orig_h / 640
        x2 = (cx + bw / 2) * orig_w / 640
        y2 = (cy + bh / 2) * orig_h / 640

        results = []
        for i in range(len(x1)):
            results.append((int(x1[i]), int(y1[i]), int(x2[i]), int(y2[i]), float(confidences[i])))

        return results

    # ---- ORIGINAL FUNCTIONS (UNCHANGED) ----

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
            forward_speed = -0.002 * offset_y
            right_speed = 0.002 * offset_x
        else:
            forward_speed = 0
            right_speed = 0

        vertical_speed = 0
        yaw_rate = 0

        return (forward_speed, right_speed, vertical_speed, yaw_rate), \
               (offset_x, offset_y, target_area, target_center_x, target_center_y)

    def _draw_hud(self, frame, x1, y1, x2, y2, measurements):
        offset_x, offset_y, target_area, target_center_x, target_center_y = measurements
        frame_center_x = self.frame_width // 2
        frame_center_y = self.frame_height // 2

        cv2.line(frame, (frame_center_x, 0), (frame_center_x, self.frame_height), (255, 255, 255), 1)
        cv2.line(frame, (0, frame_center_y), (self.frame_width, frame_center_y), (200, 200, 200), 1)

        cv2.circle(frame, (frame_center_x, frame_center_y),
                   self.horizontal_deadzone_radius, (255, 255, 0), 2)

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)

        cv2.putText(frame,
                    f"DX: {offset_x} | DY: {offset_y} | Area: {target_area}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 255, 0), 2)

        cv2.circle(frame, (target_center_x, target_center_y), 5, (0, 255, 0), -1)
