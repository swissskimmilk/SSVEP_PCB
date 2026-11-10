// Board wiring (design/mcu.circuit.json). Arduino pin numbers; nRF pins come from
// g_ADigitalPinMap at runtime so nothing here hard-codes a port.
#pragma once

#include <Arduino.h>

constexpr uint8_t PIN_ADC_CLKIN = D3;  // 8 MHz to ADS131M08 CLKIN through R5
constexpr uint8_t PIN_ANA_EN    = D4;  // analog LDO enable (+3.3V analog rail)
constexpr uint8_t PIN_ADC_SYNC  = D5;  // SYNC/RESET, R7 pull-up to the analog rail
constexpr uint8_t PIN_ADC_DRDY  = D6;  // DRDY, active low
constexpr uint8_t PIN_ADC_CS    = D7;
constexpr uint8_t PIN_ADC_SCLK  = D8;
constexpr uint8_t PIN_ADC_MISO  = D9;  // ADC DOUT
constexpr uint8_t PIN_ADC_MOSI  = D10; // ADC DIN

// ADC channel use: 0-3 EEG (INA333, gain 501), 4 photodiode (PD_OUT), 5-7 grounded.
constexpr uint8_t ADC_CHANNELS     = 8;
constexpr uint8_t DEFAULT_CH_MASK  = 0x1F;
constexpr uint8_t PD_CHANNEL       = 4;

// Absolute nRF pin number (P1.x = 32 + x) for an Arduino pin.
inline uint32_t nrf_pin(uint8_t arduino_pin) { return g_ADigitalPinMap[arduino_pin]; }

// Peripherals this firmware owns. The SoftDevice keeps TIMER0, RTC0 and PPI 17-19;
// the core's attachInterrupt() allocates GPIOTE channels from 0 upward.
#define ADC_SPIM          NRF_SPIM2
#define ADC_SPIM_IRQn     SPIM2_SPIS2_SPI2_IRQn
#define ADC_SPIM_IRQHandler SPIM2_SPIS2_SPI2_IRQHandler
#define CLK_TIMER         NRF_TIMER3
#define COUNT_TIMER       NRF_TIMER4

constexpr uint8_t GPIOTE_CH_CLK  = 7;
constexpr uint8_t GPIOTE_CH_CS   = 6;
constexpr uint8_t GPIOTE_CH_DRDY = 5;

constexpr uint8_t PPI_CH_CLK        = 10;  // CLK_TIMER compare -> toggle CLKIN
constexpr uint8_t PPI_CH_DRDY_START = 11;  // DRDY fall -> SPIM start
constexpr uint8_t PPI_CH_DRDY_CS    = 12;  // DRDY fall -> CS low
constexpr uint8_t PPI_CH_DRDY_COUNT = 13;  // DRDY fall -> sample counter
constexpr uint8_t PPI_CH_END_CS     = 14;  // SPIM end -> CS high
