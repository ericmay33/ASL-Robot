#include <Servo.h>
#include <Arduino.h>

#define NUM_SERVOS 5
Servo servos[NUM_SERVOS];
int servoPins[NUM_SERVOS] = {2, 3, 4, 5, 6}; 

void setup() {
  Serial.begin(9600);
  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].attach(servoPins[i]);
    servos[i].write(90);  // start neutral
  }
  Serial.println("Arduino Ready");
}

void loop() {
  if (Serial.available()) {
    String data = Serial.readStringUntil('\n');
    data.trim();

    // Split incoming string by commas
    int angles[NUM_SERVOS];
    int index = 0;
    char buf[data.length() + 1];
    data.toCharArray(buf, sizeof(buf));
    char *token = strtok(buf, ",");
    while (token != NULL && index < NUM_SERVOS) {
      angles[index++] = atoi(token);
      token = strtok(NULL, ",");
    }

    // Move servos to the angles
    for (int i = 0; i < NUM_SERVOS; i++) {
      servos[i].write(angles[i]);
    }

    Serial.print("Moved to: ");
    Serial.print("ACK");
    Serial.println(data);
  }
}