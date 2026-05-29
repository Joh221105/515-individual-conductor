#include <Arduino.h>
#include <Arduino_BMI270_BMM150.h>
#include <Wire.h>

constexpr int SDA_PIN = D4;
constexpr int SCL_PIN = D5;
constexpr unsigned long SAMPLE_INTERVAL_US = 10000;
constexpr int SAMPLE_COUNT = 100;

bool imuReady = false;

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {
    delay(10);
  }

  Wire.begin(SDA_PIN, SCL_PIN);
  if (!IMU.begin()) {
    Serial.println("ERROR BMI270 init failed");
    return;
  }

  imuReady = true;
  Serial.println("READY");
}

void capture() {
  if (!imuReady) {
    Serial.println("ERROR BMI270 not ready");
    return;
  }

  Serial.println("BEGIN");
  unsigned long nextSample = micros();

  for (int index = 0; index < SAMPLE_COUNT; index++) {
    while (micros() < nextSample) {
      delayMicroseconds(100);
    }
    nextSample += SAMPLE_INTERVAL_US;

    float ax = 0.0f;
    float ay = 0.0f;
    float az = 0.0f;
    float gx = 0.0f;
    float gy = 0.0f;
    float gz = 0.0f;

    if (IMU.accelerationAvailable()) {
      IMU.readAcceleration(ax, ay, az);
    }
    if (IMU.gyroscopeAvailable()) {
      IMU.readGyroscope(gx, gy, gz);
    }

    Serial.print(millis());
    Serial.print(',');
    Serial.print(ax, 6);
    Serial.print(',');
    Serial.print(ay, 6);
    Serial.print(',');
    Serial.print(az, 6);
    Serial.print(',');
    Serial.print(gx, 6);
    Serial.print(',');
    Serial.print(gy, 6);
    Serial.print(',');
    Serial.println(gz, 6);
  }

  Serial.println("END");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command == "CAPTURE") {
    capture();
  }
}
