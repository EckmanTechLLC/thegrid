// BodyPort - a deliberately dumb body for the from-nothing experiment.
//
// Contract with the universe (known to the BROKER, never to the organisms):
//   - any single byte 0..180 arriving on USB serial becomes a servo target
//   - anything else is silently ignored
//   - every 50 ms we report "P <pot-raw>" - proprioception for the broker,
//     which pays organisms for measured movement they caused
//
// Safety: slew-rate limited (so evolved chatter cannot thrash the gears),
// watchdog so a wedged sketch resets, no WiFi, no display, nothing else.

#include "mbed.h"

mbed::PwmOut servoPin(digitalPinToPinName(D2));
mbed::Watchdog &wd = mbed::Watchdog::get_instance();

float targetDeg = 90, currentDeg = 90;
unsigned long lastStep = 0, lastReport = 0;
const float MAX_DEG_PER_S = 120.0;

void setup() {
  Serial.begin(115200);
  servoPin.period_ms(20);
  wd.start(8000);
  pinMode(A0, INPUT);
  writeServo(currentDeg);
}

void writeServo(float deg) {
  int us = 500 + (int)(deg * 2000.0 / 180.0);
  servoPin.pulsewidth_us(us);
}

void loop() {
  wd.kick();
  while (Serial.available()) {
    int b = Serial.read();
    if (b >= 0 && b <= 180) targetDeg = b;
  }
  unsigned long now = millis();
  if (now - lastStep >= 10) {
    float maxStep = MAX_DEG_PER_S * (now - lastStep) / 1000.0;
    float d = targetDeg - currentDeg;
    if (d >  maxStep) d =  maxStep;
    if (d < -maxStep) d = -maxStep;
    currentDeg += d;
    writeServo(currentDeg);
    lastStep = now;
  }
  if (now - lastReport >= 50) {
    Serial.print("P ");
    Serial.println(analogRead(A0));
    lastReport = now;
  }
}
