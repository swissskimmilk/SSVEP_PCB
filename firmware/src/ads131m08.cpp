#include "ads131m08.h"

#include <Arduino.h>
#include <string.h>

#include "board.h"
#include "hw.h"

namespace ads {

uint8_t tx_frame[FRAME_BYTES];
uint8_t rx_frame[FRAME_BYTES];

static bool s_on = false;
static uint16_t s_id = 0;

static constexpr uint16_t CMD_NULL = 0x0000;
static constexpr uint16_t cmd_rreg(uint8_t addr) { return 0xA000 | (uint16_t(addr) << 7); }
static constexpr uint16_t cmd_wreg(uint8_t addr) { return 0x6000 | (uint16_t(addr) << 7); }

static void put_word(uint8_t* frame, size_t word, uint16_t v) {
    frame[word * WORD_BYTES + 0] = v >> 8;
    frame[word * WORD_BYTES + 1] = v & 0xFF;
    frame[word * WORD_BYTES + 2] = 0;
}

static uint16_t get_word(const uint8_t* frame, size_t word) {
    return (uint16_t(frame[word * WORD_BYTES]) << 8) | frame[word * WORD_BYTES + 1];
}

// ---------------------------------------------------------------- CLKIN

static void clock_start() {
    if (hw::softdevice_on()) {
        sd_clock_hfclk_request();  // CLKIN must come from the 32 MHz crystal, not the RC
        uint32_t running = 0;
        while (!running) sd_clock_hfclk_is_running(&running);
    } else {
        NRF_CLOCK->EVENTS_HFCLKSTARTED = 0;
        NRF_CLOCK->TASKS_HFCLKSTART = 1;
        while (!NRF_CLOCK->EVENTS_HFCLKSTARTED) {}
    }

    NRF_GPIOTE->CONFIG[GPIOTE_CH_CLK] =
        (GPIOTE_CONFIG_MODE_Task << GPIOTE_CONFIG_MODE_Pos) |
        hw::gpiote_psel(nrf_pin(PIN_ADC_CLKIN)) |
        (GPIOTE_CONFIG_POLARITY_Toggle << GPIOTE_CONFIG_POLARITY_Pos) |
        (GPIOTE_CONFIG_OUTINIT_Low << GPIOTE_CONFIG_OUTINIT_Pos);

    CLK_TIMER->TASKS_STOP = 1;
    CLK_TIMER->MODE = TIMER_MODE_MODE_Timer;
    CLK_TIMER->BITMODE = TIMER_BITMODE_BITMODE_16Bit;
    CLK_TIMER->PRESCALER = 0;  // 16 MHz
    CLK_TIMER->CC[0] = CLK_TIMER_CC;
    CLK_TIMER->SHORTS = TIMER_SHORTS_COMPARE0_CLEAR_Msk;
    CLK_TIMER->TASKS_CLEAR = 1;

    hw::ppi_assign(PPI_CH_CLK, &CLK_TIMER->EVENTS_COMPARE[0], &NRF_GPIOTE->TASKS_OUT[GPIOTE_CH_CLK]);
    hw::ppi_enable(1u << PPI_CH_CLK);
    CLK_TIMER->TASKS_START = 1;
}

static void clock_stop() {
    CLK_TIMER->TASKS_STOP = 1;
    hw::ppi_disable(1u << PPI_CH_CLK);
    NRF_GPIOTE->CONFIG[GPIOTE_CH_CLK] = 0;
    hw::pin_output(nrf_pin(PIN_ADC_CLKIN), false);
    if (hw::softdevice_on()) sd_clock_hfclk_release();
}

// ---------------------------------------------------------------- SPI

static void spi_begin() {
    const uint32_t cs = nrf_pin(PIN_ADC_CS);
    NRF_GPIOTE->CONFIG[GPIOTE_CH_CS] =
        (GPIOTE_CONFIG_MODE_Task << GPIOTE_CONFIG_MODE_Pos) |
        hw::gpiote_psel(cs) |
        (GPIOTE_CONFIG_POLARITY_None << GPIOTE_CONFIG_POLARITY_Pos) |
        (GPIOTE_CONFIG_OUTINIT_High << GPIOTE_CONFIG_OUTINIT_Pos);

    const uint32_t sck = nrf_pin(PIN_ADC_SCLK), mosi = nrf_pin(PIN_ADC_MOSI),
                   miso = nrf_pin(PIN_ADC_MISO);
    hw::pin_output(sck, false);
    hw::pin_output(mosi, false);
    hw::pin_input(miso);

    ADC_SPIM->ENABLE = 0;
    ADC_SPIM->PSEL.SCK = sck;
    ADC_SPIM->PSEL.MOSI = mosi;
    ADC_SPIM->PSEL.MISO = miso;
    ADC_SPIM->FREQUENCY = SPIM_FREQUENCY_FREQUENCY_M8;
    // SPI mode 1: SCLK idles low, data sampled on the falling edge.
    ADC_SPIM->CONFIG = (SPIM_CONFIG_ORDER_MsbFirst << SPIM_CONFIG_ORDER_Pos) |
                       (SPIM_CONFIG_CPHA_Trailing << SPIM_CONFIG_CPHA_Pos) |
                       (SPIM_CONFIG_CPOL_ActiveHigh << SPIM_CONFIG_CPOL_Pos);
    ADC_SPIM->ORC = 0;
    ADC_SPIM->TXD.PTR = (uint32_t)tx_frame;
    ADC_SPIM->TXD.MAXCNT = FRAME_BYTES;
    ADC_SPIM->RXD.PTR = (uint32_t)rx_frame;
    ADC_SPIM->RXD.MAXCNT = FRAME_BYTES;
    ADC_SPIM->INTENCLR = 0xFFFFFFFF;
    ADC_SPIM->ENABLE = SPIM_ENABLE_ENABLE_Enabled;

    NRF_GPIOTE->CONFIG[GPIOTE_CH_DRDY] =
        (GPIOTE_CONFIG_MODE_Event << GPIOTE_CONFIG_MODE_Pos) |
        hw::gpiote_psel(nrf_pin(PIN_ADC_DRDY)) |
        (GPIOTE_CONFIG_POLARITY_HiToLo << GPIOTE_CONFIG_POLARITY_Pos);
}

static void spi_end() {
    ADC_SPIM->ENABLE = 0;
    NRF_GPIOTE->CONFIG[GPIOTE_CH_CS] = 0;
    NRF_GPIOTE->CONFIG[GPIOTE_CH_DRDY] = 0;
}

// One full frame with manual CS. Only used while the PPI stream is stopped.
static void transfer() {
    ADC_SPIM->EVENTS_END = 0;
    NRF_GPIOTE->TASKS_CLR[GPIOTE_CH_CS] = 1;
    ADC_SPIM->TASKS_START = 1;
    while (!ADC_SPIM->EVENTS_END) {}
    ADC_SPIM->EVENTS_END = 0;
    NRF_GPIOTE->TASKS_SET[GPIOTE_CH_CS] = 1;
    delayMicroseconds(2);
}

static void command(uint16_t cmd) {
    memset(tx_frame, 0, sizeof tx_frame);
    put_word(tx_frame, 0, cmd);
    transfer();
}

// ---------------------------------------------------------------- public

void park_pins() {
    hw::pin_output(nrf_pin(PIN_ADC_CLKIN), false);
    hw::pin_output(nrf_pin(PIN_ADC_CS), false);
    hw::pin_output(nrf_pin(PIN_ADC_SCLK), false);
    hw::pin_output(nrf_pin(PIN_ADC_MOSI), false);
    hw::pin_output(nrf_pin(PIN_ADC_SYNC), false);
    hw::pin_disconnect(nrf_pin(PIN_ADC_MISO));
    hw::pin_disconnect(nrf_pin(PIN_ADC_DRDY));
}

bool power_on() {
    if (s_on) return true;
    digitalWrite(PIN_ANA_EN, HIGH);
    delay(5);  // LP5907 start-up plus ADC power-on reset

    hw::pin_output(nrf_pin(PIN_ADC_SYNC), true);
    spi_begin();
    clock_start();
    delay(1);

    // SYNC/RESET low for >= 2048 CLKIN cycles (256 us at 8 MHz) resets the ADC.
    hw::pin_output(nrf_pin(PIN_ADC_SYNC), false);
    delay(1);
    hw::pin_output(nrf_pin(PIN_ADC_SYNC), true);
    delay(1);

    s_on = true;
    s_id = read_reg(reg::ID);
    return (s_id >> 8) == 0x28;  // 0x28xx: 8 channels
}

void power_off() {
    spi_end();
    clock_stop();
    park_pins();
    digitalWrite(PIN_ANA_EN, LOW);
    s_on = false;
}

bool is_on() { return s_on; }
uint16_t id() { return s_id; }

uint16_t read_reg(uint8_t addr) {
    command(cmd_rreg(addr));
    command(CMD_NULL);  // the response arrives in the following frame
    return get_word(rx_frame, 0);
}

void write_reg(uint8_t addr, uint16_t value) {
    memset(tx_frame, 0, sizeof tx_frame);
    put_word(tx_frame, 0, cmd_wreg(addr));
    put_word(tx_frame, 1, value);
    transfer();
}

void flush() {
    command(CMD_NULL);
    command(CMD_NULL);
}

bool apply(const Config& cfg) {
    // 24-bit words, SPI timeout on, DRDY from the most lagging channel, DRDY push-pull,
    // DRDY held low until read. RESET bit written 0 to clear STATUS.RESET.
    const uint16_t mode = 0x0110;
    // All channels enabled so the frame layout never changes; high-resolution mode.
    const uint16_t clock = 0xFF00 | (uint16_t(cfg.osr_code & 7) << 2) | 0x2;
    const uint16_t gain1 = (cfg.gain[0] & 7) | (cfg.gain[1] & 7) << 4 |
                           (cfg.gain[2] & 7) << 8 | (cfg.gain[3] & 7) << 12;
    const uint16_t gain2 = (cfg.gain[4] & 7) | (cfg.gain[5] & 7) << 4 |
                           (cfg.gain[6] & 7) << 8 | (cfg.gain[7] & 7) << 12;

    write_reg(reg::MODE, mode);
    write_reg(reg::CLOCK, clock);
    write_reg(reg::GAIN1, gain1);
    write_reg(reg::GAIN2, gain2);
    for (uint8_t ch = 0; ch < ADC_CHANNELS; ch++) write_reg(reg::ch_cfg(ch), cfg.mux[ch] & 3);

    bool ok = read_reg(reg::MODE) == mode && read_reg(reg::CLOCK) == clock &&
              read_reg(reg::GAIN1) == gain1 && read_reg(reg::GAIN2) == gain2;
    for (uint8_t ch = 0; ch < ADC_CHANNELS; ch++)
        ok = ok && (read_reg(reg::ch_cfg(ch)) & 3) == (cfg.mux[ch] & 3);
    return ok;
}

uint16_t crc16(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= uint16_t(data[i]) << 8;
        for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
    }
    return crc;
}

bool frame_crc_ok(const uint8_t* frame) {
    const size_t covered = (FRAME_WORDS - 1) * WORD_BYTES;
    return crc16(frame, covered) == get_word(frame, FRAME_WORDS - 1);
}

}  // namespace ads
