// Battery, USB presence and the XIAO's RGB status LED.
#pragma once

#include <stdint.h>

namespace power {

void begin();
uint16_t battery_mv();
bool vbus_present();  // USB power: the board is tied to the laptop, so not on a person

enum class Led { Off, Advertising, Connected, Streaming, Error };
void led(Led state);  // call from loop(); handles blinking

}  // namespace power
