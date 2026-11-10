#include "acq.h"

#include <Arduino.h>
#include <string.h>

#include "ads131m08.h"
#include "board.h"
#include "hw.h"

namespace acq {

static constexpr uint32_t RING = 1024;  // ~2 s at 488 SPS
static Sample s_ring[RING];
static volatile uint32_t s_head = 0, s_tail = 0;

static volatile bool s_streaming = false;
static volatile bool s_have_last = false;
static volatile uint32_t s_last_index = 0;
static volatile uint32_t s_count = 0;
static volatile uint32_t s_dropped = 0;
static volatile uint16_t s_crc_errors = 0;
static volatile bool s_gap = false;

static constexpr uint32_t PPI_STREAM_MASK =
    (1u << PPI_CH_DRDY_START) | (1u << PPI_CH_DRDY_CS) |
    (1u << PPI_CH_DRDY_COUNT) | (1u << PPI_CH_END_CS);

extern "C" void ADC_SPIM_IRQHandler(void) {
    if (!ADC_SPIM->EVENTS_END) return;
    ADC_SPIM->EVENTS_END = 0;

    COUNT_TIMER->TASKS_CAPTURE[0] = 1;
    const uint32_t index = COUNT_TIMER->CC[0] - 1;  // DRDY already counted this frame

    if (s_have_last && index != s_last_index + 1) {
        s_dropped += index - s_last_index - 1;
        s_gap = true;
    }
    s_have_last = true;
    s_last_index = index;
    s_count = index + 1;

    const uint8_t* f = ads::rx_frame;
    const bool ok = ads::frame_crc_ok(f);
    if (!ok) s_crc_errors++;

    const uint32_t h = s_head, next = (h + 1) % RING;
    if (next == s_tail) {  // reader fell behind: drop the newest
        s_dropped++;
        s_gap = true;
        return;
    }
    Sample& s = s_ring[h];
    s.index = index;
    s.crc_ok = ok;
    s.status_hi = f[0];
    memcpy(s.data, f + ads::WORD_BYTES, sizeof s.data);
    __DMB();
    s_head = next;
}

void start() {
    if (s_streaming || !ads::is_on()) return;

    memset(ads::tx_frame, 0, ads::FRAME_BYTES);  // NULL command every frame
    ads::flush();

    COUNT_TIMER->TASKS_STOP = 1;
    COUNT_TIMER->MODE = TIMER_MODE_MODE_LowPowerCounter;
    COUNT_TIMER->BITMODE = TIMER_BITMODE_BITMODE_32Bit;
    COUNT_TIMER->TASKS_CLEAR = 1;
    COUNT_TIMER->TASKS_START = 1;

    volatile uint32_t* drdy = &NRF_GPIOTE->EVENTS_IN[GPIOTE_CH_DRDY];
    hw::ppi_assign(PPI_CH_DRDY_START, drdy, &ADC_SPIM->TASKS_START);
    hw::ppi_assign(PPI_CH_DRDY_CS, drdy, &NRF_GPIOTE->TASKS_CLR[GPIOTE_CH_CS]);
    hw::ppi_assign(PPI_CH_DRDY_COUNT, drdy, &COUNT_TIMER->TASKS_COUNT);
    hw::ppi_assign(PPI_CH_END_CS, &ADC_SPIM->EVENTS_END, &NRF_GPIOTE->TASKS_SET[GPIOTE_CH_CS]);

    s_head = s_tail = 0;
    s_have_last = false;
    s_count = 0;
    s_dropped = 0;
    s_crc_errors = 0;
    s_gap = false;

    *drdy = 0;
    ADC_SPIM->EVENTS_END = 0;
    ADC_SPIM->INTENSET = SPIM_INTENSET_END_Msk;
    NVIC_SetPriority(ADC_SPIM_IRQn, 3);  // 0, 1 and 4 belong to the SoftDevice
    NVIC_ClearPendingIRQ(ADC_SPIM_IRQn);
    NVIC_EnableIRQ(ADC_SPIM_IRQn);

    s_streaming = true;
    hw::ppi_enable(PPI_STREAM_MASK);
}

void stop() {
    if (!s_streaming) return;
    hw::ppi_disable(PPI_STREAM_MASK);
    delayMicroseconds(100);  // let a frame already in flight finish
    NVIC_DisableIRQ(ADC_SPIM_IRQn);
    ADC_SPIM->INTENCLR = SPIM_INTENCLR_END_Msk;
    ADC_SPIM->EVENTS_END = 0;
    NRF_GPIOTE->TASKS_SET[GPIOTE_CH_CS] = 1;
    COUNT_TIMER->TASKS_STOP = 1;
    s_streaming = false;
}

bool streaming() { return s_streaming; }

uint32_t available() { return (s_head + RING - s_tail) % RING; }

bool pop(Sample& out) {
    const uint32_t t = s_tail;
    if (t == s_head) return false;
    out = s_ring[t];
    __DMB();
    s_tail = (t + 1) % RING;
    return true;
}

uint32_t sample_count() { return s_count; }
uint32_t dropped() { return s_dropped; }
uint16_t crc_errors() { return s_crc_errors; }

bool take_gap() {
    if (!s_gap) return false;
    s_gap = false;
    return true;
}

}  // namespace acq
