// Hardware-driven acquisition. Each DRDY falling edge, through PPI and with no CPU:
//   CS low + SPIM start (30-byte frame by DMA) + sample counter increment.
// SPIM END raises CS and an interrupt that copies the frame into a ring buffer,
// tagged with the counter value, so a lost frame shows as a jump in the index.
#pragma once

#include <stdint.h>

namespace acq {

struct Sample {
    uint32_t index;     // ADC sample number since start()
    uint8_t crc_ok;
    uint8_t status_hi;  // STATUS register high byte (response word of a NULL frame)
    uint8_t data[24];   // 8 channels x 24-bit big-endian, as the ADC sent them
};

void start();
void stop();
bool streaming();

bool pop(Sample& out);
uint32_t available();

uint32_t sample_count();
uint32_t dropped();
uint16_t crc_errors();
bool take_gap();  // true once after any samples were lost

}  // namespace acq
