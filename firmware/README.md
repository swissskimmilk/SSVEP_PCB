# SSVEP board firmware

Seeed XIAO nRF52840, PlatformIO, Arduino (Seeed's Adafruit-based core). Reads the
ADS131M08 (EEG on channels 0–3, screen photodiode on channel 4) and streams it over BLE,
or over USB serial on the bench.

```
pio run                 # build
pio run -t upload       # flash over USB (UF2/DFU bootloader); nothing on a person
pio device monitor      # raw serial (binary COBS frames, not text)
```

`.pio/build/xiao/firmware.zip` is the OTA package: flash it over BLE with the nRF Connect
or Adafruit Bluefruit app (the firmware includes the DFU service).

## How it works

- **CLKIN (D3):** TIMER3 → PPI → GPIOTE toggle makes 8 MHz from the 32 MHz crystal, so
  the ADC sample clock is crystal-accurate. The rate is 8 MHz / 2 / OSR: 488.28 SPS at
  OSR 8192 (default), 976.56 at 4096.
- **Acquisition:** DRDY's falling edge (D6) starts a 30-byte SPIM2 DMA frame, drives CS
  low, and increments TIMER4, all through PPI. The SPIM END interrupt copies the frame
  into a ring buffer tagged with TIMER4's count. Lost frames show up as gaps in the
  sample index instead of being spliced silently.
- **Power:** the ADC rail (ANA_EN, D4) stays off until the host sends START. Until
  then every ADC-facing pin is held low or high-Z so the unpowered ADC isn't
  back-powered.
- **Protocol:** see `include/protocol.h`, which is mirrored in
  `host/ssvep_host/protocol.py`. A host test checks the two match.

Peripherals used, which the SoftDevice and the core leave free: SPIM2, TIMER3, TIMER4,
GPIOTE channels 5–7, PPI channels 10–14.

## Bring-up order

1. Flash with nothing connected. You should see the blue LED blinking (advertising).
2. In the host app, connect, then press **Start stream**. ANA_EN goes high.
   - Check +3.3 V on the analog rail and 8 MHz on R5/CLKIN with a scope.
   - Status should show `error: none`. "ADC ID mismatch" means SPI or CLKIN isn't
     working.
3. Set the channel mux to **shorted** to see the noise floor, and **+test** to confirm
   the gain.
4. Calibrate the photodiode against the screen (host app).
5. Electrodes on a person only on battery, over BLE, with the USB cable unplugged. The
   host app shows a red banner whenever the board reports USB power.

Unverified on hardware: the 8 MHz toggle rate on GPIOTE (scope it; set
`CLK_TIMER_CC = 2` in `ads131m08.h` for 4 MHz if it's unclean) and the battery divider
ratio.
