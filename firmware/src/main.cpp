#include <Arduino.h>
#include <Wire.h>
#include <Arduino_BMI270_BMM150.h>
#include <edge-impulse.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

constexpr int SDA_PIN = D4;
constexpr int SCL_PIN = D5;

// Model expects 100 Hz → 10ms per sample, 6 axes (ax ay az gx gy gz)
constexpr unsigned long SAMPLE_INTERVAL_US = 10000;

// Trigger inference when accel magnitude exceeds this (in g)
constexpr float MOTION_THRESHOLD = 1.5f;

// Minimum ms between inferences
constexpr unsigned long COOLDOWN_MS = 1500;

// Nordic UART Service UUIDs
#define BLE_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_TX_CHAR_UUID "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BLECharacteristic* pTxChar = nullptr;
bool bleConnected = false;

float features[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE];
unsigned long lastInferenceMs = 0;

class BLECallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer*) override {
        bleConnected = true;
        Serial.println("BLE connected");
    }
    void onDisconnect(BLEServer*) override {
        bleConnected = false;
        Serial.println("BLE disconnected, restarting advertising");
        BLEDevice::startAdvertising();
    }
};

void setupBLE() {
    BLEDevice::init("ConductorWand");
    BLEServer* server = BLEDevice::createServer();
    server->setCallbacks(new BLECallbacks());

    BLEService* svc = server->createService(BLE_SERVICE_UUID);
    pTxChar = svc->createCharacteristic(BLE_TX_CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    pTxChar->addDescriptor(new BLE2902());
    svc->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(BLE_SERVICE_UUID);
    adv->start();
    Serial.println("BLE advertising as 'ConductorWand'");
}

int featureGetData(size_t offset, size_t length, float* out) {
    memcpy(out, features + offset, length * sizeof(float));
    return 0;
}

void sendBleLabel(const char* label) {
    if (!bleConnected) {
        Serial.printf("BLE not connected, not sending: %s\n", label);
        return;
    }

    pTxChar->setValue((uint8_t*)label, strlen(label));
    pTxChar->notify();
    Serial.printf("BLE sent: %s\n", label);
}

void runInference() {
    Serial.println("Capturing...");
    unsigned long nextSample = micros();
    for (int i = 0; i < EI_CLASSIFIER_RAW_SAMPLE_COUNT; i++) {
        while (micros() < nextSample) delayMicroseconds(100);
        nextSample += SAMPLE_INTERVAL_US;

        float ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;
        if (IMU.accelerationAvailable()) IMU.readAcceleration(ax, ay, az);
        if (IMU.gyroscopeAvailable())    IMU.readGyroscope(gx, gy, gz);

        int base = i * 6;
        features[base + 0] = ax;
        features[base + 1] = ay;
        features[base + 2] = az;
        features[base + 3] = gx;
        features[base + 4] = gy;
        features[base + 5] = gz;
    }

    signal_t signal;
    signal.total_length = EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE;
    signal.get_data = &featureGetData;

    ei_impulse_result_t result = {};
    EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);
    if (err != EI_IMPULSE_OK) {
        Serial.printf("Inference error: %d\n", err);
        return;
    }

    int bestIdx = 0;
    for (int i = 1; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
        if (result.classification[i].value > result.classification[bestIdx].value)
            bestIdx = i;
    }

    const char* label = result.classification[bestIdx].label;
    float conf = result.classification[bestIdx].value;
    Serial.printf("Gesture: %s (%.2f)\n", label, conf);

    if (strcmp(label, "idle") == 0) {
        Serial.println("BLE not sending idle");
    }
    else {
        sendBleLabel(label);
    }

    lastInferenceMs = millis();
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) delay(10);

    Wire.begin(SDA_PIN, SCL_PIN);
    if (!IMU.begin()) {
        Serial.println("ERROR: BMI270 init failed");
        return;
    }
    Serial.println("IMU ready");
    setupBLE();
}

void loop() {
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd == "INFER") runInference();
        else if (cmd.startsWith("BLETEST ")) {
            String label = cmd.substring(8);
            label.trim();
            if (label.length() > 0) sendBleLabel(label.c_str());
        }
        return;
    }

    if (millis() - lastInferenceMs < COOLDOWN_MS) return;

    if (IMU.accelerationAvailable()) {
        float ax, ay, az;
        IMU.readAcceleration(ax, ay, az);
        float mag = sqrtf(ax * ax + ay * ay + az * az);
        if (mag > MOTION_THRESHOLD) runInference();
    }
    delay(10);
}
