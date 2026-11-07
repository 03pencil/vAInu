#include <Arduino_RouterBridge.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

// Receives one frame from Python (scripts/led_matrix.py) as 104 characters
// of '0' and '1', row by row, 8 rows x 13 columns.

const int ROWS = 8;
const int COLS = 13;

ArduinoLEDMatrix matrix;
String pendingFrame = "";
bool newFrame = false;

void showFrame(String bits) {
  if (bits.length() == ROWS * COLS) {
    pendingFrame = bits;
    newFrame = true;
  }
}

void setup() {
  matrix.begin();
  Bridge.begin();
  Bridge.provide("show_frame", showFrame);
}

void loop() {
  Bridge.update();
  if (newFrame) {
    matrix.beginDraw();
    for (int y = 0; y < ROWS; y++) {
      for (int x = 0; x < COLS; x++) {
        bool on = pendingFrame.charAt(y * COLS + x) == '1';
        matrix.set(x, y, on ? 255 : 0, on ? 255 : 0, on ? 255 : 0);
      }
    }
    matrix.endDraw();
    newFrame = false;
  }
  delay(10);
}
