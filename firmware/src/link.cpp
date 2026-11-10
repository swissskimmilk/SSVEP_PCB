#include "link.h"

#include <Arduino.h>
#include <bluefruit.h>

#include "cobs.h"
#include "protocol.h"

namespace link {

static const uint8_t UUID_SVC[16] = SSVEP_UUID_BYTES(0x01);
static const uint8_t UUID_DATA[16] = SSVEP_UUID_BYTES(0x02);
static const uint8_t UUID_CTRL[16] = SSVEP_UUID_BYTES(0x03);
static const uint8_t UUID_STATUS[16] = SSVEP_UUID_BYTES(0x04);

static BLEDfu s_dfu;  // OTA updates through the stock bootloader
static BLEService s_svc(UUID_SVC);
static BLECharacteristic s_data(UUID_DATA);
static BLECharacteristic s_ctrl(UUID_CTRL);
static BLECharacteristic s_status(UUID_STATUS);

static volatile uint16_t s_conn = BLE_CONN_HANDLE_INVALID;
static QueueHandle_t s_commands;

static void enqueue(const uint8_t* data, uint16_t len) {
    if (len == 0 || len > MAX_COMMAND) return;
    Command c;
    c.len = len;
    memcpy(c.data, data, len);
    xQueueSend(s_commands, &c, 0);
}

static void on_connect(uint16_t conn) {
    s_conn = conn;
    BLEConnection* c = Bluefruit.Connection(conn);
    c->requestPHY();  // 2M
    c->requestDataLengthUpdate();
    c->requestMtuExchange(247);
}

static void on_disconnect(uint16_t conn, uint8_t reason) {
    (void)conn;
    (void)reason;
    s_conn = BLE_CONN_HANDLE_INVALID;
    // Losing the link stops the stream so a reconnect starts clean.
    const uint8_t stop = CMD_STOP;
    enqueue(&stop, 1);
}

static void on_ctrl_write(uint16_t conn, BLECharacteristic* chr, uint8_t* data, uint16_t len) {
    (void)conn;
    (void)chr;
    enqueue(data, len);  // executed in loop(), never in the BLE task
}

void begin() {
    s_commands = xQueueCreate(8, sizeof(Command));

    Serial.begin(115200);

    Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
    Bluefruit.begin();
    Bluefruit.autoConnLed(false);
    Bluefruit.setTxPower(4);
    Bluefruit.setName("SSVEP");
    Bluefruit.Periph.setConnectCallback(on_connect);
    Bluefruit.Periph.setDisconnectCallback(on_disconnect);
    Bluefruit.Periph.setConnInterval(6, 12);  // 7.5-15 ms

    s_dfu.begin();
    s_svc.begin();

    s_data.setProperties(CHR_PROPS_NOTIFY);
    s_data.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
    s_data.setMaxLen(MAX_PAYLOAD);
    s_data.begin();

    s_ctrl.setProperties(CHR_PROPS_WRITE | CHR_PROPS_WRITE_WO_RESP);
    s_ctrl.setPermission(SECMODE_OPEN, SECMODE_OPEN);
    s_ctrl.setMaxLen(MAX_COMMAND);
    s_ctrl.setWriteCallback(on_ctrl_write);
    s_ctrl.begin();

    s_status.setProperties(CHR_PROPS_READ | CHR_PROPS_NOTIFY);
    s_status.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
    s_status.setMaxLen(sizeof(StatusPacket));
    s_status.begin();

    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addService(s_svc);
    Bluefruit.ScanResponse.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(32, 244);  // 20 ms fast, 152.5 ms slow
    Bluefruit.Advertising.setFastTimeout(30);
    Bluefruit.Advertising.start(0);
}

void poll() {
    static uint8_t buf[cobs::max_encoded(MAX_COMMAND) + 1];
    static size_t n = 0;
    while (Serial.available()) {
        const int b = Serial.read();
        if (b < 0) break;
        if (b == 0) {
            uint8_t cmd[MAX_COMMAND + 1];
            const size_t len = n <= sizeof buf ? cobs::decode(buf, n, cmd) : 0;
            enqueue(cmd, len);
            n = 0;
        } else if (n < sizeof buf) {
            buf[n++] = b;
        } else {
            n = sizeof buf + 1;  // overlong: drop until the next delimiter
        }
    }
}

bool ble_connected() { return s_conn != BLE_CONN_HANDLE_INVALID; }

bool ble_streaming() { return ble_connected() && s_data.notifyEnabled(s_conn); }

bool usb_open() { return bool(Serial); }

uint16_t max_payload() {
    uint16_t m = MAX_PAYLOAD;
    if (ble_connected()) {
        BLEConnection* c = Bluefruit.Connection(s_conn);
        if (c) m = min<uint16_t>(m, c->getMtu() - 3);
    }
    return m;
}

static void usb_write(const uint8_t* pkt, uint16_t len) {
    uint8_t enc[cobs::max_encoded(MAX_PAYLOAD) + 1];
    const size_t n = cobs::encode(pkt, len, enc);
    enc[n] = 0;
    if (Serial.availableForWrite() >= int(n + 1)) Serial.write(enc, n + 1);
}

bool send_data(const uint8_t* pkt, uint16_t len, bool usb_already_sent, bool& usb_sent) {
    usb_sent = usb_already_sent;
    if (!usb_sent && usb_open()) {
        usb_write(pkt, len);
        usb_sent = true;
    }
    if (!ble_streaming()) return true;
    return s_data.notify(s_conn, pkt, len);
}

void send_status(const uint8_t* pkt, uint16_t len) {
    s_status.write(pkt, len);
    if (ble_connected() && s_status.notifyEnabled(s_conn)) s_status.notify(s_conn, pkt, len);
    if (usb_open()) usb_write(pkt, len);
}

bool pop_command(Command& out) { return xQueueReceive(s_commands, &out, 0) == pdTRUE; }

}  // namespace link
