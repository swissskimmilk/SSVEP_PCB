// Host links: BLE (the only one to use on a person) and USB CDC (bench only).
#pragma once

#include <stdint.h>

namespace link {

constexpr uint8_t MAX_COMMAND = 20;

struct Command {
    uint8_t len;
    uint8_t data[MAX_COMMAND];
};

void begin();
void poll();  // read USB bytes into the command queue

bool ble_connected();
bool ble_streaming();    // connected and data notifications enabled
bool usb_open();
uint16_t max_payload();  // largest data packet every active link accepts

// Data: BLE gets it if subscribed (returns false if its buffers are full, so the
// caller retries the same packet); USB gets it once when open, best effort.
bool send_data(const uint8_t* pkt, uint16_t len, bool usb_already_sent, bool& usb_sent);
void send_status(const uint8_t* pkt, uint16_t len);

bool pop_command(Command& out);

}  // namespace link
