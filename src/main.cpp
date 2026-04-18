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

constexpr float kFilterRateHz = 100.0f;
constexpr auto kFilterPeriod = 10ms;
constexpr int kGyroBiasSamples = 300;
constexpr int kWarmupSamples = 50;

// thread
Thread blinkThread(osPriorityHigh, OS_STACK_SIZE, nullptr, "IMU_Task");

// 
Madgwick filter;

struct GyroBias {
    float x;
    float y;
    float z;
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
    float ax = 0.0, ay = 0.0, az = 0.0;
    float gx = 0.0, gy = 0.0, gz = 0.0;
    float roll = 0.0, pitch = 0.0, yaw = 0.0;

    IMU.debug(Serial);
    if(!(IMU.begin(BOSCH_ACCELEROMETER_ONLY))){
        while(1){
            Serial.println("Failed to initialize IMU!");
            ThisThread::sleep_for(100ms);
        }
    }

    GyroBias gyroBias = calibrateGyroBias();
    filter.begin(kFilterRateHz);

    Serial.println("AHRS started in 6-axis mode.");

    while(true) {
        if(IMU.accelerationAvailable() && IMU.gyroscopeAvailable()){
            IMU.readAcceleration(ax, ay, az);
            IMU.readGyroscope(gx, gy, gz);
            gx -= gyroBias.x;
            gy -= gyroBias.y;
            gz -= gyroBias.z;
            filter.updateIMU(gx, gy, gz, ax, ay, az);
        
            roll = filter.getRoll();
            pitch = filter.getPitch();
            yaw = filter.getYaw();

            Serial.print(roll);
            Serial.print(",");
            Serial.print(pitch);
            Serial.print(",");
            Serial.println(yaw);
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
