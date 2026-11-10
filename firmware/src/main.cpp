// SSVEP board firmware: ADS131M08 (EEG ch0-3, photodiode ch4) streamed to the host.
// The photodiode is sampled in the same frame as the EEG, so the host aligns
// stimuli to EEG by sample index; nothing here needs wall-clock timestamps.

#include <Arduino.h>
#include <string.h>

#include "acq.h"
#include "ads131m08.h"
#include "board.h"
#include "link.h"
#include "power.h"
#include "protocol.h"

#ifndef FW_VERSION
#define FW_VERSION 0
#endif

static ads::Config s_cfg;
static uint8_t s_ch_mask = DEFAULT_CH_MASK;
static bool s_configured = false;
static uint8_t s_error = ERR_NONE;
static uint16_t s_battery_mv = 0;

// One data packet in flight; kept until BLE accepts it.
static uint8_t s_pkt[MAX_PAYLOAD];
static uint16_t s_pkt_len = 0;
static bool s_pkt_usb_sent = false;
static uint32_t s_pkt_started_ms = 0;

static void send_status() {
    StatusPacket st = {};
    st.type = PKT_STATUS;
    st.fw_version = FW_VERSION;
    st.flags = (ads::is_on() ? STATUS_FLAG_ANALOG_ON : 0) |
               (acq::streaming() ? STATUS_FLAG_STREAMING : 0) |
               (power::vbus_present() ? STATUS_FLAG_VBUS : 0) |
               (link::ble_connected() ? STATUS_FLAG_BLE : 0) |
               (link::usb_open() ? STATUS_FLAG_USB_CDC : 0) |
               (s_configured ? STATUS_FLAG_ADC_OK : 0);
    st.osr_code = s_cfg.osr_code;
    st.battery_mv = s_battery_mv;
    st.adc_id = ads::id();
    st.clkin_khz = ads::CLKIN_HZ / 1000;
    st.sample_count = acq::sample_count();
    st.dropped = acq::dropped();
    st.crc_errors = acq::crc_errors();
    st.ch_mask = s_ch_mask;
    st.error = s_error;
    memcpy(st.gain, s_cfg.gain, 8);
    memcpy(st.mux, s_cfg.mux, 8);
    link::send_status(reinterpret_cast<const uint8_t*>(&st), sizeof st);
}

static bool analog_up() {
    if (!ads::is_on()) {
        s_configured = false;
        if (!ads::power_on()) {
            s_error = ERR_ADC_ID;
            ads::power_off();
            return false;
        }
    }
    if (!s_configured) {
        if (!ads::apply(s_cfg)) {
            s_error = ERR_ADC_VERIFY;
            return false;
        }
        s_configured = true;
        s_error = ERR_NONE;
    }
    return true;
}

static void start_stream() {
    if (acq::streaming()) return;
    if (!analog_up()) return;
    s_pkt_len = 0;
    acq::start();
}

static void stop_stream() {
    acq::stop();
    s_pkt_len = 0;
}

// Settings change: restart the stream around the register writes.
static void reconfigure() {
    const bool was = acq::streaming();
    stop_stream();
    s_configured = false;
    if (ads::is_on()) analog_up();
    if (was) start_stream();
}

static void handle(const link::Command& c) {
    const uint8_t* a = c.data + 1;
    const uint8_t n = c.len - 1;
    switch (c.data[0]) {
        case CMD_START: start_stream(); break;
        case CMD_STOP: stop_stream(); break;
        case CMD_SET_OSR:
            if (n < 1 || a[0] > 7) goto bad;
            s_cfg.osr_code = a[0];
            reconfigure();
            break;
        case CMD_SET_GAIN:
            if (n < 2 || a[0] >= ADC_CHANNELS || a[1] > 7) goto bad;
            s_cfg.gain[a[0]] = a[1];
            reconfigure();
            break;
        case CMD_SET_MUX:
            if (n < 2 || a[0] >= ADC_CHANNELS || a[1] > 3) goto bad;
            s_cfg.mux[a[0]] = a[1];
            reconfigure();
            break;
        case CMD_SET_MASK:
            if (n < 1 || a[0] == 0) goto bad;
            s_pkt_len = 0;
            s_ch_mask = a[0];
            break;
        case CMD_ANALOG_OFF:
            stop_stream();
            ads::power_off();
            s_configured = false;
            break;
        case CMD_STATUS: break;
        default: goto bad;
    }
    send_status();
    return;
bad:
    s_error = ERR_BAD_COMMAND;
    send_status();
}

static uint8_t popcount8(uint8_t v) {
    uint8_t n = 0;
    for (; v; v &= v - 1) n++;
    return n;
}

// Move samples from the ring into s_pkt and push it out. Packets close when full
// or 40 ms after their first sample, so the host sees a steady trickle.
static void pump_data() {
    const uint8_t nch = popcount8(s_ch_mask);
    const uint16_t per_sample = nch * 3;
    const uint8_t max_samples = (link::max_payload() - sizeof(DataHeader)) / per_sample;

    if (s_pkt_len == 0 && acq::available()) {
        DataHeader h = {};
        h.type = PKT_DATA;
        h.ch_mask = s_ch_mask;
        memcpy(s_pkt, &h, sizeof h);
        s_pkt_len = sizeof h;
        s_pkt_usb_sent = false;
        s_pkt_started_ms = millis();
    }
    if (s_pkt_len == 0) return;

    DataHeader* h = reinterpret_cast<DataHeader*>(s_pkt);
    acq::Sample s;
    while (h->n_samples < max_samples && acq::pop(s)) {
        if (h->n_samples == 0) h->first_index = s.index;
        if (!s.crc_ok) h->flags |= DATA_FLAG_CRC_ERROR;
        uint8_t* p = s_pkt + s_pkt_len;
        for (uint8_t ch = 0; ch < ADC_CHANNELS; ch++) {
            if (!(s_ch_mask & (1u << ch))) continue;
            memcpy(p, s.data + ch * 3, 3);
            p += 3;
        }
        s_pkt_len += per_sample;
        h->n_samples++;
    }
    if (acq::take_gap()) h->flags |= DATA_FLAG_GAP;

    const bool full = h->n_samples >= max_samples;
    const bool old = h->n_samples > 0 && millis() - s_pkt_started_ms >= 40;
    if (!full && !old) return;

    bool usb_sent;
    if (link::send_data(s_pkt, s_pkt_len, s_pkt_usb_sent, usb_sent)) s_pkt_len = 0;
    else s_pkt_usb_sent = usb_sent;  // BLE busy: retry the same packet next loop
}

void setup() {
    // ADC unpowered until a START: every pin facing it must be low or high-Z first.
    pinMode(PIN_ANA_EN, OUTPUT);
    digitalWrite(PIN_ANA_EN, LOW);
    ads::park_pins();

    power::begin();
    link::begin();
    s_battery_mv = power::battery_mv();
}

void loop() {
    link::poll();
    link::Command c;
    while (link::pop_command(c)) handle(c);

    if (acq::streaming()) pump_data();

    static uint32_t last_status = 0, last_battery = 0;
    const uint32_t now = millis();
    if (now - last_battery >= 5000) {
        last_battery = now;
        s_battery_mv = power::battery_mv();
    }
    if (now - last_status >= 1000) {
        last_status = now;
        send_status();
    }

    if (s_error != ERR_NONE) power::led(power::Led::Error);
    else if (acq::streaming()) power::led(power::Led::Streaming);
    else if (link::ble_connected() || link::usb_open()) power::led(power::Led::Connected);
    else power::led(power::Led::Advertising);

    if (!acq::streaming()) delay(5);
    else yield();
}
