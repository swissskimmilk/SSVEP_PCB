// Wire protocol shared by BLE and USB. Mirrored in host/ssvep_host/protocol.py;
// change both together.
//
// BLE: one packet per notification / write. USB CDC: each packet COBS-encoded and
// terminated by 0x00. All multi-byte header fields are little-endian; ADC samples
// are passed through as the ADC sends them (24-bit two's complement, big-endian).
#pragma once

#include <stdint.h>

// Service a3c40001-5b6e-4f8a-9d2c-7e1f0b5c3a91; characteristics differ in byte 12.
#define SSVEP_UUID_BYTES(x) \
    {0x91, 0x3a, 0x5c, 0x0b, 0x1f, 0x7e, 0x2c, 0x9d, 0x8a, 0x4f, 0x6e, 0x5b, (x), 0x00, 0xc4, 0xa3}

constexpr uint8_t PKT_DATA   = 0x01;
constexpr uint8_t PKT_STATUS = 0x02;

// Data packet: header, then n_samples x popcount(ch_mask) x 3 bytes.
struct __attribute__((packed)) DataHeader {
    uint8_t  type;        // PKT_DATA
    uint8_t  n_samples;
    uint8_t  ch_mask;
    uint8_t  flags;       // DATA_FLAG_*
    uint32_t first_index; // ADC sample index of the first sample (counts every DRDY)
};
constexpr uint8_t DATA_FLAG_CRC_ERROR = 0x01; // a frame in this packet failed the ADC CRC
constexpr uint8_t DATA_FLAG_GAP       = 0x02; // samples were lost before this packet

constexpr uint16_t MAX_PAYLOAD = 244; // ATT MTU 247 - 3

struct __attribute__((packed)) StatusPacket {
    uint8_t  type;        // PKT_STATUS
    uint8_t  fw_version;
    uint8_t  flags;       // STATUS_FLAG_*
    uint8_t  osr_code;    // ADS131M08 CLOCK.OSR[2:0]
    uint16_t battery_mv;
    uint16_t adc_id;
    uint16_t clkin_khz;   // ADC master clock; sample rate = clkin / 2 / OSR
    uint32_t sample_count;
    uint32_t dropped;     // samples lost to a full ring or a missed frame
    uint16_t crc_errors;
    uint8_t  ch_mask;
    uint8_t  error;       // ERR_*
    uint8_t  gain[8];     // PGAGAIN code per channel (gain = 1 << code)
    uint8_t  mux[8];      // MUX code per channel
};
constexpr uint8_t STATUS_FLAG_ANALOG_ON = 0x01;
constexpr uint8_t STATUS_FLAG_STREAMING = 0x02;
constexpr uint8_t STATUS_FLAG_VBUS      = 0x04; // USB power present: not safe on a person
constexpr uint8_t STATUS_FLAG_BLE       = 0x08;
constexpr uint8_t STATUS_FLAG_USB_CDC   = 0x10;
constexpr uint8_t STATUS_FLAG_ADC_OK    = 0x20;

constexpr uint8_t ERR_NONE          = 0;
constexpr uint8_t ERR_ADC_ID        = 1; // ID register did not read 0x28xx
constexpr uint8_t ERR_ADC_VERIFY    = 2; // register read-back mismatch
constexpr uint8_t ERR_BAD_COMMAND   = 3;

// Commands (control characteristic / USB): opcode then arguments.
constexpr uint8_t CMD_START      = 0x01;
constexpr uint8_t CMD_STOP       = 0x02;
constexpr uint8_t CMD_SET_OSR    = 0x03; // [osr_code]
constexpr uint8_t CMD_SET_GAIN   = 0x04; // [channel, gain_code]
constexpr uint8_t CMD_SET_MUX    = 0x05; // [channel, mux_code]
constexpr uint8_t CMD_SET_MASK   = 0x06; // [ch_mask]
constexpr uint8_t CMD_ANALOG_OFF = 0x07;
constexpr uint8_t CMD_STATUS     = 0x08;
