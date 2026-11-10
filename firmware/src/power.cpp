#include "power.h"

#include <Arduino.h>
#include <nrf_soc.h>

#include "hw.h"

#ifndef VBAT_ENABLE
#define VBAT_ENABLE 14  // P0.14: low connects the XIAO's battery divider
#endif
#ifndef PIN_VBAT
#define PIN_VBAT 32     // P0.31 / AIN7
#endif

namespace power {

// XIAO divider: 1 M over 510 k. Calibrate against a meter if the reading matters.
static constexpr float VBAT_DIVIDER = 1510.0f / 510.0f;

void begin() {
    // Keep P0.14 low permanently. Driven high while charging, the pin sees the
    // battery through the divider and can be damaged.
    pinMode(VBAT_ENABLE, OUTPUT);
    digitalWrite(VBAT_ENABLE, LOW);

    pinMode(LED_RED, OUTPUT);
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_BLUE, OUTPUT);
    led(Led::Off);

    analogReference(AR_INTERNAL_2_4);
    analogReadResolution(12);
}

uint16_t battery_mv() {
    uint32_t sum = 0;
    for (int i = 0; i < 8; i++) sum += analogRead(PIN_VBAT);
    const float v = (sum / 8.0f) * 2.4f / 4095.0f * VBAT_DIVIDER;
    return uint16_t(v * 1000.0f);
}

bool vbus_present() {
    uint32_t status = 0;
    if (hw::softdevice_on()) sd_power_usbregstatus_get(&status);
    else status = NRF_POWER->USBREGSTATUS;
    return status & POWER_USBREGSTATUS_VBUSDETECT_Msk;
}

static void rgb(bool r, bool g, bool b) {  // LEDs are active low
    digitalWrite(LED_RED, !r);
    digitalWrite(LED_GREEN, !g);
    digitalWrite(LED_BLUE, !b);
}

void led(Led state) {
    const uint32_t t = millis();
    switch (state) {
        case Led::Off:         rgb(false, false, false); break;
        case Led::Advertising: rgb(false, false, (t % 2000) < 60); break;
        case Led::Connected:   rgb(false, (t % 2000) < 60, false); break;
        case Led::Streaming:   rgb(false, (t % 500) < 60, false); break;
        case Led::Error:       rgb((t % 400) < 200, false, false); break;
    }
}

}  // namespace power
