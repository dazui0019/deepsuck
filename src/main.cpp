#include <Arduino.h>
#include <Wire.h>
#include <rtos.h>
#include "SparkFun_BMI270_Arduino_Library.h"

using namespace rtos;
using namespace std::chrono_literals;

const int ledPin = PIN_LED;
const int ledR = LEDR;
const int ledG = LEDG;
const int ledB = LEDB;

uint8_t i2cAddress = BMI2_I2C_PRIM_ADDR; // 0x68
BMI270 imu;

// thread
Thread blinkThread(osPriorityHigh, OS_STACK_SIZE, nullptr, "IMU_Task");

void imuTask() {
    Wire1.begin();

    while(imu.beginI2C(i2cAddress, Wire1) != BMI2_OK){
        // Not connected, inform user
        Serial.println("Error: BMI270 not connected, check wiring and I2C address!");

        // Wait a bit to see if connection is established
        delay(1000);
    }

    Serial.println("BMI270 connected!");
    
    while(true){
        // Get measurements from the sensor. This must be called before accessing
        // the sensor data, otherwise it will never update
        imu.getSensorData();

        // Print acceleration data
        Serial.print("Acceleration in g's");
        Serial.print("\t");
        Serial.print("X: ");
        Serial.print(imu.data.accelX, 3);
        Serial.print("\t");
        Serial.print("Y: ");
        Serial.print(imu.data.accelY, 3);
        Serial.print("\t");
        Serial.print("Z: ");
        Serial.print(imu.data.accelZ, 3);

        Serial.print("\t");

        // Print rotation data
        Serial.print("Rotation in deg/sec");
        Serial.print("\t");
        Serial.print("X: ");
        Serial.print(imu.data.gyroX, 3);
        Serial.print("\t");
        Serial.print("Y: ");
        Serial.print(imu.data.gyroY, 3);
        Serial.print("\t");
        Serial.print("Z: ");
        Serial.println(imu.data.gyroZ, 3);

        // Print 50x per second
        delay(20);
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
