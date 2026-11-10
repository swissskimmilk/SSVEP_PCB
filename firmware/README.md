# Firmware

XIAO nRF52840, PlatformIO, Arduino (Seeed's nRF52 core).

```
pio run                # build
pio run -t upload      # flash over USB
```

`.pio/build/xiao/firmware.zip` is the over-the-air update package; flash it with the
nRF Connect app.

| File | Job |
|---|---|
| `ads131m08.cpp` | ADC power-up, 8 MHz clock, registers |
| `acq.cpp` | DRDY → SPI read → ring buffer, all triggered in hardware |
| `link.cpp` | BLE service, USB serial |
| `power.cpp` | Battery, USB detect, LED |
| `main.cpp` | Commands, packets, status |

LED: blue blink means advertising, slow green means connected, fast green means
streaming, red means error.

To check on first power-up: 8 MHz on CLKIN (set `CLK_TIMER_CC = 2` for 4 MHz if it
isn't clean), and the battery reading against a meter.
