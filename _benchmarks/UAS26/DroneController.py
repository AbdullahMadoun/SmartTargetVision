# ***pip install pymavlink
from pymavlink import mavutil

class DroneController:
    def __init__(self, connection_string, baud_rate):
        self.vehicle = mavutil.mavlink_connection(connection_string, baud = baud_rate)
        self._last_heartbeat = self.vehicle.wait_heartbeat()
        self._last_mode = self._decode_mode(self._last_heartbeat)
        self._last_armed = self._decode_armed(self._last_heartbeat)

    def _decode_mode(self, heartbeat):
        return self.vehicle.flightmode

    def _decode_armed(self, heartbeat):
        return self.vehicle.motors_armed()

    def refresh_flight_state(self, blocking=True, timeout=1.5):
        heartbeat = self.vehicle.recv_match(type='HEARTBEAT', blocking=blocking, timeout=timeout)
        if heartbeat is None:
            heartbeat = self.vehicle.messages.get('HEARTBEAT')

        if heartbeat is not None:
            self._last_heartbeat = heartbeat
            self._last_mode = self._decode_mode(heartbeat)
            self._last_armed = self._decode_armed(heartbeat)

        return self._last_mode, self._last_armed

    def get_current_mode(self, blocking=False, timeout=0.0):
        mode, _ = self.refresh_flight_state(blocking=blocking, timeout=timeout)
        return mode

    def is_armed(self, blocking=False, timeout=0.0):
        _, armed = self.refresh_flight_state(blocking=blocking, timeout=timeout)
        return armed

    def tracking_is_authorized(self, allowed_modes=('GUIDED',), blocking=False, timeout=0.0):
        mode, armed = self.refresh_flight_state(blocking=blocking, timeout=timeout)
        return armed and mode in allowed_modes
    
    def send_velocity_cmd(self, x, y, z, yaw):  #x = forward/backward, y = left/right, z = up/down
        self.vehicle.mav.set_position_target_local_ned_send(
            0,
            self.vehicle.target_system,
            self.vehicle.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_NED,
            0b010111000111, # mask to ignore position/accel, enable velocity and yaw
            0, 0, 0,        # ignore position
            x, y, z,        # velocity
            0, 0, 0,        # ignore acceleration
            0, yaw          # yaw, yaw rate
        )
