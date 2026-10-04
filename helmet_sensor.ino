#include <Wire.h>

// Pin Configuration
const uint8_t FSR_PIN = A0;
const uint8_t VIBRATION_PIN = 2;
const uint8_t CANCEL_BUTTON_PIN = 3;
const uint8_t BUZZER_PIN = 8;
const uint8_t GREEN_LED_PIN = 9;
const uint8_t RED_LED_PIN = 10;

// Sensor Configuration
const uint8_t MPU6050_ADDRESS = 0x68;
const unsigned long SAMPLE_INTERVAL_MS = 100;

// Variables
unsigned long lastSampleTime = 0;
bool mpu6050Ready = false;
bool buzzerState = false;
bool redLedState = false;
bool greenLedState = true;

struct MpuReading {
  float ax;
  float ay;
  float az;
  float gx;
  float gy;
  float gz;
};

void writeMpuRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU6050_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool readMpu6050(MpuReading &reading) {
  Wire.beginTransmission(MPU6050_ADDRESS);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MPU6050_ADDRESS, (uint8_t)14) != 14) {
    return false;
  }

  int16_t rawAx = (Wire.read() << 8) | Wire.read();
  int16_t rawAy = (Wire.read() << 8) | Wire.read();
  int16_t rawAz = (Wire.read() << 8) | Wire.read();
  Wire.read();
  Wire.read();
  int16_t rawGx = (Wire.read() << 8) | Wire.read();
  int16_t rawGy = (Wire.read() << 8) | Wire.read();
  int16_t rawGz = (Wire.read() << 8) | Wire.read();

  // MPU6050 defaults: accelerometer +/-2g and gyroscope +/-250 deg/s.
  reading.ax = rawAx / 16384.0;
  reading.ay = rawAy / 16384.0;
  reading.az = rawAz / 16384.0;
  reading.gx = rawGx / 131.0;
  reading.gy = rawGy / 131.0;
  reading.gz = rawGz / 131.0;
  return true;
}

void setOutputs() {
  digitalWrite(BUZZER_PIN, buzzerState ? HIGH : LOW);
  digitalWrite(RED_LED_PIN, redLedState ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, greenLedState ? HIGH : LOW);
}

void handleCommand(String command) {
  command.trim();
  if (command == "BUZZER_ON") buzzerState = true;
  else if (command == "BUZZER_OFF") buzzerState = false;
  else if (command == "RED_ON") redLedState = true;
  else if (command == "RED_OFF") redLedState = false;
  else if (command == "GREEN_ON") greenLedState = true;
  else if (command == "GREEN_OFF") greenLedState = false;
  else if (command == "RESET") {
    buzzerState = false;
    redLedState = false;
    greenLedState = true;
  }
  // Unknown commands are intentionally ignored.
  setOutputs();
}

void receiveCommands() {
  if (Serial.available() == 0) return;
  String command = Serial.readStringUntil('\n');
  handleCommand(command);
}

void setup() {
  pinMode(VIBRATION_PIN, INPUT);
  pinMode(CANCEL_BUTTON_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  setOutputs();

  Serial.begin(115200);
  Wire.begin();
  writeMpuRegister(0x6B, 0x00);
  delay(50);

  Wire.beginTransmission(MPU6050_ADDRESS);
  mpu6050Ready = (Wire.endTransmission() == 0);
  if (!mpu6050Ready) {
    Serial.println("ERROR,MPU6050");
  }
}

void loop() {
  receiveCommands();

  unsigned long now = millis();
  if (now - lastSampleTime < SAMPLE_INTERVAL_MS) return;
  lastSampleTime = now;

  if (!mpu6050Ready) {
    Serial.println("ERROR,MPU6050");
    return;
  }

  MpuReading reading;
  if (!readMpu6050(reading)) {
    Serial.println("ERROR,MPU6050");
    return;
  }

  int fsrValue = analogRead(FSR_PIN);
  int vibration = digitalRead(VIBRATION_PIN) == HIGH ? 1 : 0;
  int cancel = digitalRead(CANCEL_BUTTON_PIN) == LOW ? 1 : 0;

  Serial.print("DATA,");
  Serial.print(reading.ax, 3); Serial.print(",");
  Serial.print(reading.ay, 3); Serial.print(",");
  Serial.print(reading.az, 3); Serial.print(",");
  Serial.print(reading.gx, 2); Serial.print(",");
  Serial.print(reading.gy, 2); Serial.print(",");
  Serial.print(reading.gz, 2); Serial.print(",");
  Serial.print(fsrValue); Serial.print(",");
  Serial.print(vibration); Serial.print(",");
  Serial.println(cancel);
}
