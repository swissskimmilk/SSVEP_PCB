// Small register helpers for PPI and GPIOTE. PPI goes through the SoftDevice API
// while the SoftDevice is enabled (direct writes to PPI are not allowed then).
#pragma once

#include <Arduino.h>
#include <nrf_soc.h>
#include <nrf_sdm.h>

namespace hw {

inline bool softdevice_on() {
    uint8_t en = 0;
    sd_softdevice_is_enabled(&en);
    return en;
}

inline void ppi_assign(uint8_t ch, volatile uint32_t* event, volatile uint32_t* task) {
    if (softdevice_on()) {
        sd_ppi_channel_assign(ch, event, task);
    } else {
        NRF_PPI->CH[ch].EEP = (uint32_t)event;
        NRF_PPI->CH[ch].TEP = (uint32_t)task;
    }
}

inline void ppi_enable(uint32_t mask) {
    if (softdevice_on()) sd_ppi_channel_enable_set(mask);
    else NRF_PPI->CHENSET = mask;
}

inline void ppi_disable(uint32_t mask) {
    if (softdevice_on()) sd_ppi_channel_enable_clr(mask);
    else NRF_PPI->CHENCLR = mask;
}

inline uint32_t gpiote_psel(uint32_t pin) {
    return ((pin & 31) << GPIOTE_CONFIG_PSEL_Pos) | ((pin >> 5) << GPIOTE_CONFIG_PORT_Pos);
}

inline NRF_GPIO_Type* port(uint32_t pin) { return pin < 32 ? NRF_P0 : NRF_P1; }

// Input with the buffer disconnected: draws nothing and drives nothing.
inline void pin_disconnect(uint32_t pin) {
    port(pin)->PIN_CNF[pin & 31] =
        (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos);
}

inline void pin_output(uint32_t pin, bool high) {
    if (high) port(pin)->OUTSET = 1u << (pin & 31);
    else port(pin)->OUTCLR = 1u << (pin & 31);
    port(pin)->PIN_CNF[pin & 31] =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos);
}

inline void pin_input(uint32_t pin) {
    port(pin)->PIN_CNF[pin & 31] =
        (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos);
}

}  // namespace hw
