#include <Arduino.h>
#include <rtos.h>
#include "Arduino_BMI270_BMM150.h"

using namespace rtos;
using namespace std::chrono_literals;

const int ledPin = PIN_LED;
const int ledR = LEDR;
const int ledG = LEDG;
const int ledB = LEDB;

// thread
Thread blinkThread(osPriorityHigh, OS_STACK_SIZE, nullptr, "IMU_Task");

void imuTask() {
    float acce[3] = {0, 0, 0};
    while(true) {
        if(IMU.accelerationAvailable()){
            IMU.readAcceleration(acce[0], acce[1], acce[2]);

            Serial.print(acce[0]);
            Serial.print(',');
            Serial.print(acce[1]);
            Serial.print(',');
            Serial.println(acce[2]);
        }
        ThisThread::sleep_for(100ms);
    }
}

void setup() {
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

    if(!(IMU.begin(BOSCH_ACCELEROMETER_ONLY))){
        Serial.println("Failed to initialize IMU!");
        while (1){}
    }

    Serial.print("Acceleration sample rate = ");
    Serial.print(IMU.accelerationSampleRate());
    Serial.println(" Hz");

    blinkThread.start(imuTask);
}

void loop() {
    digitalWrite(ledPin, !digitalRead(ledPin));
    ThisThread::sleep_for(200ms);
}
