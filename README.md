# Smart Helmet Accident Detection System

## Project Overview

Smart Helmet Accident Detection System is a Python-assisted Arduino safety prototype that combines an MPU6050 accelerometer/gyroscope, vibration sensor, and pressure sensor to monitor helmet usage and detect patterns associated with possible accidents. Arduino collects the physical sensor data and communicates with a Python desktop application over USB serial. Python processes the sensor readings, displays real-time information, logs data, and manages an accident warning and confirmation workflow.

This is an educational prototype, not a certified medical, automotive, or safety device.

## Objectives

- Detect pressure at the helmet sensor location.
- Monitor acceleration, angular velocity, vibration, and approximate tilt.
- Combine multiple indicators to reduce false accident warnings.
- Provide a cancellable warning countdown and confirmed emergency state.
- Display live readings and save a CSV log.

## Features

- Arduino UNO sensor bridge at 115200 baud.
- MPU6050 readings in g and degrees per second.
- Configurable FSR, impact, tilt, score, time-window, and countdown thresholds.
- Tkinter desktop dashboard with COM-port selection.
- Background serial thread so the GUI remains responsive.
- Red/green LEDs and buzzer controlled by Python commands.
- Runtime-created `helmet_data.csv` sensor log.
- Safe handling of invalid data, missing MPU6050, serial errors, and disconnects.

## Hardware Components

- Arduino UNO
- MPU6050 accelerometer and gyroscope
- FSR/pressure sensor and resistor for a voltage divider
- Digital vibration sensor
- Buzzer
- Red LED and green LED with suitable resistors
- Push button
- Breadboard, jumper wires, USB cable, and helmet shell/model

Optional future hardware such as GPS, GSM, ESP32, Wi-Fi, and cloud services is not implemented in this version.

## Software Requirements

- Arduino IDE
- Python 3
- `pyserial` from `requirements.txt`
- Tkinter, normally included with Python

## System Architecture

```text
MPU6050 + vibration + FSR + button
                |
            Arduino UNO
                |
          USB serial, 115200
                |
       Python worker thread
                |
   detection + logging + Tkinter
```

Arduino only collects readings and controls outputs. Python performs accident detection.

## Circuit Connections

### MPU6050

| MPU6050 | Arduino UNO |
| --- | --- |
| SDA | A4 |
| SCL | A5 |
| VCC | Appropriate module voltage |
| GND | GND |

### Other connections

| Component | Arduino pin |
| --- | --- |
| FSR voltage-divider output | A0 |
| Vibration sensor | D2 |
| Cancel button | D3 to GND, using `INPUT_PULLUP` |
| Buzzer | D8 |
| Green LED | D9 through a resistor |
| Red LED | D10 through a resistor |

The button reads LOW when pressed and HIGH when released. Confirm the voltage requirements of the MPU6050 breakout board before powering it.

## Pin Configuration

The exact pin mapping is defined at the top of `helmet_sensor.ino`. The FSR is sent as a raw analog value; Python decides whether it is worn using `HELMET_THRESHOLD = 500`.

## Arduino Setup

1. Install the Arduino IDE.
2. Open `helmet_sensor.ino`.
3. Select **Arduino UNO** under Board.
4. Select the correct COM port.
5. Connect the components according to the tables above.
6. Upload the sketch.
7. Open Serial Monitor only for inspection, using 115200 baud. Close it before starting Python.

The sketch uses the Arduino `Wire` library and communicates directly with the MPU6050, so no third-party Arduino library is required.

## Python Setup

Open a terminal inside this project folder and run:

```text
pip install -r requirements.txt
```

Start the dashboard with:

```text
python accident_detection.py
```

Choose the Arduino COM port, then click **Connect**. `COM3` is only a default example; use the port shown by Arduino IDE or the dashboard refresh list.

## Installation

The final project initially contains only these four files:

```text
helmet_sensor.ino
accident_detection.py
requirements.txt
README.md
```

The application creates `helmet_data.csv` automatically at runtime when readings arrive. It is not included manually in the project.

## Running the Project

1. Connect the hardware and USB cable.
2. Upload the Arduino sketch.
3. Find the port in Arduino IDE under **Tools > Port**, then close Serial Monitor.
4. Install the Python requirement.
5. Run `python accident_detection.py`.
6. Select the port and click **Connect**.
7. Verify live acceleration, tilt, FSR helmet status, vibration, and connection status.
8. Use **RESET SYSTEM** to return from an emergency state to monitoring.

## Accident Detection Logic

Python calculates:

```text
acceleration_magnitude = sqrt(ax^2 + ay^2 + az^2)
```

Pitch and roll are approximate accelerometer-based angles and are not a highly accurate orientation system.

Default prototype thresholds are:

- `HELMET_THRESHOLD = 500`
- `IMPACT_THRESHOLD = 2.5 g`
- `TILT_THRESHOLD = 60 degrees`
- `ACCIDENT_SCORE_THRESHOLD = 2`
- `ACCIDENT_WINDOW = 3 seconds`
- `CANCEL_TIME = 10 seconds`

Within the event window, the indicators are impact, abnormal tilt, vibration, and helmet pressure. A score of two starts `ACCIDENT_WARNING`. Vibration alone never confirms an accident. During the warning, press the physical cancel button. If it is not cancelled within 10 seconds, the state becomes `ACCIDENT_CONFIRMED` and remains there until **RESET SYSTEM** is pressed.

These values are experimental and are not medically or scientifically validated.

## Dashboard

The dashboard shows connection, helmet status, acceleration, magnitude, gyroscope, tilt, vibration, system state, accident state, countdown, and messages. Normal, warning, and emergency states are shown as `MONITORING`, `WARNING`, and `EMERGENCY`.

## Serial Communication

Arduino sends approximately 10 packets per second:

```text
DATA,ax,ay,az,gx,gy,gz,fsr,vibration,cancel
```

Example:

```text
DATA,0.120,0.040,1.010,2.30,-1.40,0.80,650,0,0
```

Acceleration is in g, gyroscope values are in degrees per second, FSR is a raw 0-1023 ADC value, and digital fields are 0 or 1. If the MPU6050 cannot initialize or be read, Arduino sends `ERROR,MPU6050`.

Python sends these newline-terminated commands:

```text
BUZZER_ON
BUZZER_OFF
RED_ON
RED_OFF
GREEN_ON
GREEN_OFF
RESET
```

Unknown commands are ignored by Arduino.

## Data Logging

When data arrives, Python creates or appends to `helmet_data.csv` with these columns:

```text
timestamp, ax, ay, az, gx, gy, gz, acceleration_magnitude, pitch, roll, helmet, vibration, accident_state
```

## Testing

Use a safe bench setup. Do not intentionally crash, hit, or endanger a person.

1. Confirm Arduino appears under **Tools > Port**.
2. Check MPU6050 values by moving it carefully by hand.
3. Press the FSR and verify `WORN`; release it and verify `NOT WORN`.
4. Trigger the vibration sensor with controlled vibration.
5. Press the cancel button and verify its wiring.
6. Connect Python and verify live serial data.
7. Verify all dashboard values update without freezing.
8. Simulate a warning using careful movement and controlled vibration.
9. Press cancel during the countdown and verify return to monitoring.
10. Allow a safe simulated warning to reach confirmation.
11. Press **RESET SYSTEM** and verify the normal state returns.
12. Open the runtime CSV and verify rows and headers.

## Limitations

The FSR only detects pressure/contact at its sensor location and does not prove that a helmet is correctly worn. Accelerometer tilt is approximate, thresholds require calibration, and this prototype has no GPS, GSM, cloud service, machine learning, or emergency-contact notification. Serial disconnection also prevents live detection.

## Future Improvements

Possible future upgrades include ESP32, Wi-Fi, Blynk, GPS NEO-6M, GSM/SMS, a cloud database, a mobile application, machine-learning accident classification, emergency contact notification, and real-time location sharing. Future datasets could collect acceleration, gyroscope, tilt, vibration, helmet status, and accident labels to classify `Normal`, `Sudden Movement`, `Fall`, and `Possible Accident`. Machine learning is not implemented in this version.

## Safety Disclaimer

This project is an educational prototype and must not be treated as a certified motorcycle safety system or medical emergency device. Thresholds are experimental and require extensive validation before any real-world safety application.

## Developer

Smart Helmet Accident Detection System project.
