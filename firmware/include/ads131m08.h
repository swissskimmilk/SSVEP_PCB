// ADS131M08 driver: power sequencing, CLKIN generation, register access.
// Register map and frame format: TI SBAS950B sections 8.5.1 and 8.6.
#pragma once

#include <stdint.h>
#include <stddef.h>

namespace ads {

// CLKIN from TIMER3 + PPI + GPIOTE: 16 MHz / (2 * CLK_TIMER_CC). CC=1 gives 8 MHz.
constexpr uint32_t CLK_TIMER_CC = 1;
constexpr uint32_t CLKIN_HZ = 16000000 / (2 * CLK_TIMER_CC);

constexpr size_t WORD_BYTES = 3;                 // 24-bit words (MODE.WLENGTH = 01b)
constexpr size_t FRAME_WORDS = 10;               // response + 8 channels + CRC
constexpr size_t FRAME_BYTES = FRAME_WORDS * WORD_BYTES;

namespace reg {
constexpr uint8_t ID = 0x00, STATUS = 0x01, MODE = 0x02, CLOCK = 0x03,
                  GAIN1 = 0x04, GAIN2 = 0x05, CFG = 0x06;
constexpr uint8_t ch_cfg(uint8_t ch) { return 0x09 + 5 * ch; }
}  // namespace reg

constexpr uint8_t OSR_4096 = 5;  // 976.56 SPS at 8 MHz
constexpr uint8_t OSR_8192 = 6;  // 488.28 SPS at 8 MHz

struct Config {
    uint8_t osr_code = OSR_8192;
    uint8_t gain[8] = {0, 0, 0, 0, 0, 0, 0, 0};  // PGA gain = 1 << code, code 0..7
    uint8_t mux[8] = {0, 0, 0, 0, 0, 0, 0, 0};   // 0 normal, 1 shorted, 2 +test, 3 -test
};

// Hold every ADC-facing pin low or high-Z. Call at boot before anything else:
// with ANA_EN low the ADC is unpowered and would back-power through its pins.
void park_pins();

// ANA_EN high, start CLKIN, reset the ADC, check its ID. False if the ID is wrong.
bool power_on();
void power_off();
bool is_on();
uint16_t id();

bool apply(const Config& cfg);  // write and read back MODE, CLOCK, GAIN, CHn_CFG

uint16_t read_reg(uint8_t addr);
void write_reg(uint8_t addr, uint16_t value);
void flush();  // read two frames, emptying the ADC's 2-deep output FIFO

uint16_t crc16(const uint8_t* data, size_t len);  // CCITT, seed 0xFFFF
bool frame_crc_ok(const uint8_t* frame);

// DMA buffers used by both the blocking transfers here and the PPI-driven stream.
extern uint8_t tx_frame[FRAME_BYTES];
extern uint8_t rx_frame[FRAME_BYTES];

}  // namespace ads
