## Wiring up the Jetson to the Cube
- Jetson Orin Nano --> Orange Cube
- Pin 8 (UART_1 TX) --> Pin 3 (RX)
- Pin 10 (UART_1 RX) --> Pin 2 (TX)
- Pin 6 (GND) --> Pin 6 (GND)

## Flight Controller Config
- In mission planner go to *Config > Full Parameter List*
- Update the following parameters to configure the jetson orin nano on the TELEM 2 port:
  - SERIAL2_PROTOCOL = 2
  - SERIAL2_BAUD = 921 (921600 baud rate)
- Click Write Params and reboot the flight controller

## Code Checklist
- In *main*:
  - Comment out the UDP simulation string and uncomment the jetson serial string
  - Change this:
  ```python
  drone = DroneController(connection_string = 'udp:172.25.48.1:14551', baud_rate = 115200) #Use when simulating

  # drone = DroneController(connection_string='/dev/ttyTHS1', baud_rate=921600) #Use when on jetson
  ```
  - To this:
  ```python
  # drone = DroneController(connection_string = 'udp:172.25.48.1:14551', baud_rate = 115200) #Use when simulating
  
  drone = DroneController(connection_string='/dev/ttyTHS1', baud_rate=921600) #Use when on jetson
  ```
  
- In *PersonTracker*:
  - Comment out the Windows camera setting and uncomment the jetson camera setting
  - Change this:
  ```bash
  # self.cap = cv2.VideoCapture(camera_index)   #FOR JETSON NANO
  self.cap = cv2.VideoCapture(2, cv2.CAP_DSHOW) #FOR WINDOWS
  ```
  - To this:
  ```bash
  self.cap = cv2.VideoCapture(camera_index)   #FOR JETSON NANO
  # self.cap = cv2.VideoCapture(2, cv2.CAP_DSHOW) #FOR WINDOWS
  ```
## Jetson Orin Nano Setup
- Open the terminal and run the following command to allow your user profile to read and write to the UART port (/dev/ttyTHS1) and access the USB camera:
  ```bash
  sudo usermod -a -G dialout $USER
  sudo usermod -a -G video $USER
  sudo systemctl stop nvgetty
  sudo systemctl disable nvgetty
  udevadm trigger
  ```
  - reboot to apply the permission changes
  - Open a new terminal. Ubuntu 22.04 requires Python packages to be installed in a Virtual Environment. Create and activate it using the following commands:
  ```bash
  sudo apt-get update
  sudo apt-get install -y python3-venv libopenblas-dev python3-opencv
  python3 -m venv drone_env --system-site-packages
  source drone_env/bin/activate
  ```
  - note: You will need to run source drone_env/bin/activate every time you open a new terminal to run your drone code
  - Install NVIDIA's GPU-accelerated Pytorch for JetPack 6.0:
  ```bash
  pip3 install torch torchvision --index-url https://pypi.jetson-ai-lab.io/jp6/cu122
  ```
  - install the remaining python dependencies inside the environment
  ```bash
  pip3 install pymavlink ultralytics numpy
  ```

## Execution Steps
- Ensure all python files and the model file are placed in the same directory.
- Power on the drone system and wait for the orange cube to complete its boot sequence and acquire a GPS lock.
- note: the code assumes the drone has already taken off since otherwise the camera, which is placed at the bottom, will not be able to see anything.
- switch the drone's flight mode to **guided**
- activate the environment, change directory to the folder containing the python files and run the main script on the jetson nano:
```bash
source drone_env/bin/activate
python3 main.py
```

## Troubleshooting Guide from gpt

**Issue: The script hangs at "Initializing Flight Controller Connection..."**
* **Cause:** The Jetson is not receiving a heartbeat from the Orange Cube.
* **Fix 1:** Verify your TX and RX wires are crossed (Jetson TX must go to Cube RX, and vice versa).
* **Fix 2:** Verify `SERIAL2_BAUD` is exactly `921` in Mission Planner, and matches `baud_rate=921600` in `main.py`.
* **Fix 3:** Check UART permissions. Run `ls -l /dev/ttyTHS1`. If you don't see `dialout` or if you didn't reboot after adding the user group, the script will be denied access.

**Issue: Camera Loading Error / Script crashes immediately.**
* **Cause:** OpenCV cannot find or access the USB camera.
* **Fix 1:** Run `ls -l /dev/video*` in the terminal. Note the number (e.g., `/dev/video0`). Ensure `camera_index=0` in `main.py` matches this number.
* **Fix 2:** Verify you changed the `cv2.VideoCapture` line in `PersonTracker.py` (removing the Windows `cv2.CAP_DSHOW` backend).

**Issue: Drone ignores commands or immediately switches back to LOITER/HOLD.**
* **Cause:** The flight controller is rejecting GUIDED mode.
* **Fix:** ArduPilot will reject GUIDED mode if it does not have a good GPS fix (EKF variance is too high). Ensure you are outdoors with a strong GPS signal, or if indoors, ensure your optical flow/lidar sensors are correctly configured and healthy.

**Issue: The video feed is extremely laggy or the script gets "Killed".**
* **Cause:** The Jetson Orin Nano is running out of memory (OOM), or the TensorRT engine is failing to load on the GPU.
* **Fix 1:** Ensure you exported the YOLO `.engine` file *specifically* on this exact Jetson device. TensorRT engines are tied to the exact GPU architecture they are built on; you cannot copy an `.engine` file from a PC to an Orin Nano.
* **Fix 2:** If the terminal simply outputs "Killed", you have run out of RAM. You must create a Swap File (at least 4GB to 8GB) on your Jetson Orin Nano to prevent memory crashes during inference.

  
