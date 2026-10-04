"""Smart Helmet Arduino serial dashboard and prototype accident detector."""

import csv
import math
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import serial
from serial import SerialException
from serial.tools import list_ports


# Configuration
SERIAL_PORT = "COM3"
BAUD_RATE = 115200
HELMET_THRESHOLD = 500
IMPACT_THRESHOLD = 2.5
TILT_THRESHOLD = 60.0
ACCIDENT_SCORE_THRESHOLD = 2
ACCIDENT_WINDOW = 3.0
CANCEL_TIME = 10.0
LOG_FILE = Path(__file__).with_name("helmet_data.csv")


@dataclass
class SensorData:
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    fsr: int
    vibration: int
    cancel: int
    timestamp: float

    @property
    def acceleration_magnitude(self) -> float:
        return math.sqrt(self.ax**2 + self.ay**2 + self.az**2)

    @property
    def pitch(self) -> float:
        return math.degrees(math.atan2(self.ax, math.sqrt(self.ay**2 + self.az**2)))

    @property
    def roll(self) -> float:
        return math.degrees(math.atan2(self.ay, math.sqrt(self.ax**2 + self.az**2)))

    @property
    def helmet(self) -> bool:
        return self.fsr >= HELMET_THRESHOLD


def parse_data_line(line: str) -> SensorData:
    fields = line.strip().split(",")
    if len(fields) != 10 or fields[0] != "DATA":
        raise ValueError("Expected DATA followed by 9 values")
    values = [float(value) for value in fields[1:7]]
    fsr = int(fields[7])
    vibration = int(fields[8])
    cancel = int(fields[9])
    if vibration not in (0, 1) or cancel not in (0, 1):
        raise ValueError("Digital sensor fields must be 0 or 1")
    return SensorData(*values, fsr, vibration, cancel, time.time())


class AccidentDetector:
    def __init__(self, command_sender):
        self.command_sender = command_sender
        self.state = "MONITORING"
        self.indicator_events = []
        self.warning_started = None
        self.cancel_seen = False

    def _set_outputs(self, normal: bool) -> None:
        self.command_sender("GREEN_ON" if normal else "GREEN_OFF")
        self.command_sender("RED_OFF" if normal else "RED_ON")
        self.command_sender("BUZZER_OFF" if normal else "BUZZER_ON")

    def _start_warning(self, now: float) -> None:
        self.state = "ACCIDENT_WARNING"
        self.warning_started = now
        self.cancel_seen = False
        self._set_outputs(normal=False)

    def process(self, data: SensorData) -> None:
        now = data.timestamp
        if self.state == "ACCIDENT_CONFIRMED":
            return
        if self.state == "ACCIDENT_WARNING":
            if data.cancel:
                self.cancel_seen = True
                self.state = "MONITORING"
                self.warning_started = None
                self.indicator_events.clear()
                self._set_outputs(normal=True)
                return
            if self.warning_started is not None and now - self.warning_started >= CANCEL_TIME:
                self.state = "ACCIDENT_CONFIRMED"
                self._set_outputs(normal=False)
            return

        indicators = set()
        if data.acceleration_magnitude >= IMPACT_THRESHOLD:
            indicators.add("impact")
        if abs(data.pitch) >= TILT_THRESHOLD or abs(data.roll) >= TILT_THRESHOLD:
            indicators.add("tilt")
        if data.vibration:
            indicators.add("vibration")
        if data.helmet:
            indicators.add("helmet")
        if indicators:
            self.indicator_events.append((now, indicators))
        self.indicator_events = [
            event for event in self.indicator_events if now - event[0] <= ACCIDENT_WINDOW
        ]
        score = len(set().union(*(event[1] for event in self.indicator_events))) if self.indicator_events else 0
        if score >= ACCIDENT_SCORE_THRESHOLD:
            self._start_warning(now)

    def tick(self) -> None:
        if self.state != "ACCIDENT_WARNING" or self.warning_started is None:
            return
        if time.time() - self.warning_started >= CANCEL_TIME:
            self.state = "ACCIDENT_CONFIRMED"
            self._set_outputs(normal=False)

    def reset(self) -> None:
        self.state = "MONITORING"
        self.indicator_events.clear()
        self.warning_started = None
        self.cancel_seen = False
        self.command_sender("RESET")

    @property
    def countdown(self) -> int:
        if self.state != "ACCIDENT_WARNING" or self.warning_started is None:
            return 0
        return max(0, math.ceil(CANCEL_TIME - (time.time() - self.warning_started)))


class SerialWorker(threading.Thread):
    def __init__(self, port: str, event_queue: queue.Queue):
        super().__init__(daemon=True)
        self.port = port
        self.event_queue = event_queue
        self.stop_event = threading.Event()
        self.serial_connection = None
        self.write_lock = threading.Lock()
        self.detector = AccidentDetector(self.send_command)

    def send_command(self, command: str) -> None:
        if self.serial_connection and self.serial_connection.is_open:
            try:
                with self.write_lock:
                    self.serial_connection.write((command + "\n").encode("ascii"))
            except SerialException as error:
                self.event_queue.put(("error", f"Serial write error: {error}"))

    def stop(self) -> None:
        self.stop_event.set()
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()

    def _log_data(self, data: SensorData) -> None:
        new_file = not LOG_FILE.exists()
        with LOG_FILE.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow([
                    "timestamp", "ax", "ay", "az", "gx", "gy", "gz",
                    "acceleration_magnitude", "pitch", "roll", "helmet",
                    "vibration", "accident_state",
                ])
            writer.writerow([
                datetime.now().isoformat(timespec="seconds"), data.ax, data.ay,
                data.az, data.gx, data.gy, data.gz,
                round(data.acceleration_magnitude, 3), round(data.pitch, 2),
                round(data.roll, 2), "WORN" if data.helmet else "NOT WORN",
                "DETECTED" if data.vibration else "NORMAL", self.detector.state,
            ])

    def run(self) -> None:
        try:
            self.serial_connection = serial.Serial(self.port, BAUD_RATE, timeout=0.1)
            self.event_queue.put(("connected", self.port))
            self.send_command("RESET")
            while not self.stop_event.is_set():
                self.detector.tick()
                raw_line = self.serial_connection.readline()
                if not raw_line:
                    continue
                line = raw_line.decode("ascii", errors="replace").strip()
                if line == "ERROR,MPU6050":
                    self.event_queue.put(("mpu_error", line))
                    continue
                try:
                    data = parse_data_line(line)
                except (ValueError, TypeError):
                    self.event_queue.put(("invalid", line))
                    continue
                self.detector.process(data)
                self._log_data(data)
                self.event_queue.put(("data", data, self.detector.state, self.detector.countdown))
        except (SerialException, OSError) as error:
            self.event_queue.put(("error", f"Could not open {self.port}: {error}"))
        finally:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            self.event_queue.put(("disconnected", self.port))


class Dashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Smart Helmet Accident Detection")
        self.root.geometry("640x620")
        self.root.minsize(560, 520)
        self.events = queue.Queue()
        self.worker = None
        self.labels = {}
        self._build_ui()
        self.refresh_ports()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="SMART HELMET ACCIDENT DETECTION", font=("Segoe UI", 16, "bold")).pack(pady=(0, 12))

        connection = ttk.Frame(frame)
        connection.pack(fill="x", pady=4)
        ttk.Label(connection, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value=SERIAL_PORT)
        self.port_box = ttk.Combobox(connection, textvariable=self.port_var, width=14, state="normal")
        self.port_box.pack(side="left", padx=6)
        ttk.Button(connection, text="Refresh", command=self.refresh_ports).pack(side="left")
        ttk.Button(connection, text="Connect", command=self.connect).pack(side="left", padx=4)
        ttk.Button(connection, text="Disconnect", command=self.disconnect).pack(side="left")

        self._add_status(frame, "Connection", "DISCONNECTED")
        self._add_status(frame, "Helmet", "UNKNOWN")
        self._add_status(frame, "Acceleration", "X: -- g   Y: -- g   Z: -- g")
        self._add_status(frame, "Magnitude", "-- g")
        self._add_status(frame, "Pitch / Roll", "-- / -- degrees")
        self._add_status(frame, "Gyroscope", "X: --   Y: --   Z: -- deg/s")
        self._add_status(frame, "Vibration", "UNKNOWN")
        self._add_status(frame, "System", "MONITORING")
        self._add_status(frame, "Accident", "NO")
        self._add_status(frame, "Countdown", "--")
        self._add_status(frame, "Message", "Ready")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=16)
        ttk.Button(buttons, text="RESET SYSTEM", command=self.reset).pack(side="left")
        ttk.Button(buttons, text="EXIT", command=self.close).pack(side="right")

    def _add_status(self, parent, name: str, value: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=f"{name}:", width=18, anchor="w").pack(side="left")
        label = ttk.Label(row, text=value)
        label.pack(side="left", fill="x", expand=True)
        self.labels[name] = label

    def refresh_ports(self) -> None:
        ports = [port.device for port in list_ports.comports()]
        self.port_box["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def connect(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("Port required", "Select or enter the Arduino COM port.")
            return
        self.labels["Connection"].configure(text="CONNECTING")
        self.worker = SerialWorker(port, self.events)
        self.worker.start()

    def disconnect(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.labels["Connection"].configure(text="DISCONNECTED")

    def reset(self) -> None:
        if self.worker:
            self.worker.detector.reset()
            self.labels["System"].configure(text="MONITORING")
            self.labels["Accident"].configure(text="NO")
            self.labels["Countdown"].configure(text="--")

    def process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "connected":
                    self.labels["Connection"].configure(text=f"CONNECTED ({event[1]})")
                    self.labels["Message"].configure(text="Arduino connected")
                elif kind == "disconnected":
                    self.labels["Connection"].configure(text="DISCONNECTED")
                elif kind == "mpu_error":
                    self.labels["Message"].configure(text="MPU6050 ERROR")
                elif kind == "invalid":
                    self.labels["Message"].configure(text="Invalid serial data ignored")
                elif kind == "error":
                    self.labels["Connection"].configure(text="DISCONNECTED")
                    self.labels["Message"].configure(text=event[1])
                elif kind == "data":
                    self.update_sensor_view(event[1], event[2], event[3])
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def update_sensor_view(self, data: SensorData, state: str, countdown: int) -> None:
        self.labels["Helmet"].configure(text="WORN" if data.helmet else "NOT WORN")
        self.labels["Acceleration"].configure(text=f"X: {data.ax:.2f} g   Y: {data.ay:.2f} g   Z: {data.az:.2f} g")
        self.labels["Magnitude"].configure(text=f"{data.acceleration_magnitude:.2f} g")
        self.labels["Pitch / Roll"].configure(text=f"{data.pitch:.1f} / {data.roll:.1f} degrees")
        self.labels["Gyroscope"].configure(text=f"X: {data.gx:.1f}   Y: {data.gy:.1f}   Z: {data.gz:.1f} deg/s")
        self.labels["Vibration"].configure(text="DETECTED" if data.vibration else "NORMAL")
        self.labels["System"].configure(text={"MONITORING": "MONITORING", "ACCIDENT_WARNING": "WARNING", "ACCIDENT_CONFIRMED": "EMERGENCY"}.get(state, state))
        self.labels["Accident"].configure(text={"MONITORING": "NO", "ACCIDENT_WARNING": "POSSIBLE", "ACCIDENT_CONFIRMED": "CONFIRMED"}.get(state, state))
        self.labels["Countdown"].configure(text=f"Cancel within {countdown} seconds" if state == "ACCIDENT_WARNING" else "--")
        if state == "ACCIDENT_WARNING":
            self.labels["Message"].configure(text="POSSIBLE ACCIDENT DETECTED")
        elif state == "ACCIDENT_CONFIRMED":
            self.labels["Message"].configure(text="ACCIDENT CONFIRMED")

    def close(self) -> None:
        if self.worker:
            self.worker.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
