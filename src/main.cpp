#include <Arduino.h>
#include <rtos.h>
#include "Arduino_BMI270_BMM150.h"
#include "MadgwickAHRS.h"

using namespace rtos;
using namespace std::chrono_literals;

const int ledPin = PIN_LED;
const int ledR = LEDR;
const int ledG = LEDG;
const int ledB = LEDB;

constexpr auto kFilterPeriod = 10ms;
constexpr float kFilterPeriodSeconds = 0.01f;
constexpr int kGyroBiasSamples = 300;
constexpr int kWarmupSamples = 50;
constexpr float kAccelLowPassCutoffHz = 5.0f;
constexpr float kGyroLowPassCutoffHz = 8.0f;

// thread
Thread blinkThread(osPriorityHigh, OS_STACK_SIZE, nullptr, "IMU_Task");

// 
Madgwick filter;

struct GyroBias {
    float x;
    float y;
    float z;
};

struct LowPassFilter {
    float alpha;
    float state;
    bool initialized;

    explicit LowPassFilter(float cutoffHz)
        : alpha(computeAlpha(cutoffHz)), state(0.0f), initialized(false) {}

    static float computeAlpha(float cutoffHz) {
        if (cutoffHz <= 0.0f) {
            return 1.0f;
        }
        const float rc = 1.0f / (2.0f * PI * cutoffHz);
        return kFilterPeriodSeconds / (rc + kFilterPeriodSeconds);
    }

    float apply(float input) {
        if (!initialized) {
            state = input;
            initialized = true;
            return state;
        }

        state += alpha * (input - state);
        return state;
    }
};

static GyroBias calibrateGyroBias() {
    float gx = 0.0f;
    float gy = 0.0f;
    float gz = 0.0f;
    GyroBias bias{0.0f, 0.0f, 0.0f};

    Serial.println("Keep IMU still, calibrating gyro bias...");

    for (int i = 0; i < kWarmupSamples; ++i) {
        if (IMU.gyroscopeAvailable()) {
            IMU.readGyroscope(gx, gy, gz);
        }
        ThisThread::sleep_for(kFilterPeriod);
    }

    int samples = 0;
    while (samples < kGyroBiasSamples) {
        if (IMU.gyroscopeAvailable()) {
            IMU.readGyroscope(gx, gy, gz);
            bias.x += gx;
            bias.y += gy;
            bias.z += gz;
            ++samples;
        }
        ThisThread::sleep_for(kFilterPeriod);
    }

    bias.x /= kGyroBiasSamples;
    bias.y /= kGyroBiasSamples;
    bias.z /= kGyroBiasSamples;

    Serial.print("Gyro bias(dps): ");
    Serial.print(bias.x, 4);
    Serial.print(", ");
    Serial.print(bias.y, 4);
    Serial.print(", ");
    Serial.println(bias.z, 4);

    return bias;
}

void imuTask() {
    float ax = 0.0, ay = 0.0, az = 0.0; // 加速度
    float gx = 0.0, gy = 0.0, gz = 0.0; // 角速度
    LowPassFilter accelFilterX(kAccelLowPassCutoffHz);
    LowPassFilter accelFilterY(kAccelLowPassCutoffHz);
    LowPassFilter accelFilterZ(kAccelLowPassCutoffHz);
    LowPassFilter gyroFilterX(kGyroLowPassCutoffHz);
    LowPassFilter gyroFilterY(kGyroLowPassCutoffHz);
    LowPassFilter gyroFilterZ(kGyroLowPassCutoffHz);

    IMU.debug(Serial);
    if(!(IMU.begin(BOSCH_ACCELEROMETER_ONLY))){
        while(1){
            Serial.println("Failed to initialize IMU!");
            ThisThread::sleep_for(100ms);
        }
    }

    GyroBias gyroBias = calibrateGyroBias();

    Serial.println("AHRS started in 6-axis mode.");

    while(true) {
        if(IMU.accelerationAvailable()){
            IMU.readAcceleration(ax, ay, az);
            IMU.readGyroscope(gx, gy, gz);

            gx -= gyroBias.x;
            gy -= gyroBias.y;
            gz -= gyroBias.z;

            ax = accelFilterX.apply(ax);
            ay = accelFilterY.apply(ay);
            az = accelFilterZ.apply(az);
            gx = gyroFilterX.apply(gx);
            gy = gyroFilterY.apply(gy);
            gz = gyroFilterZ.apply(gz);

            Serial.print(ax, 4);
            Serial.print(",");
            Serial.print(ay, 4);
            Serial.print(",");
            Serial.print(az, 4);
            Serial.print(",");
            Serial.print(gx, 4);
            Serial.print(",");
            Serial.print(gy, 4);
            Serial.print(",");
            Serial.println(gz, 4);
        }
        ThisThread::sleep_for(kFilterPeriod);
    }
}

void setup(){
    // led init
    pinMode(ledPin, OUTPUT);
    pinMode(ledR, OUTPUT);
    pinMode(ledG, OUTPUT);
    pinMode(ledB, OUTPUT);

    // debug 灯, 点亮
    digitalWrite(ledPin, HIGH);

    // RGB 灯, 熄灭
    digitalWrite(ledR, HIGH);
    digitalWrite(ledG, HIGH);
    digitalWrite(ledB, HIGH);
    Serial.begin(115200);
    while(!Serial){}

    blinkThread.start(imuTask);
}

void loop(){
    digitalWrite(ledPin, !digitalRead(ledPin));
    ThisThread::sleep_for(200ms);
}
