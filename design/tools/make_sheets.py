"""make_sheets.py -- our three hand-placed KiCad sheets for the SSVEP board.

    python make_sheets.py        # writes SSVEP_PCB/SSVEP_PCB/sheets/{power,mcu,photodiode}.kicad_sch

Every coordinate below is chosen by hand (mm, 1.27 grid). Cross-sheet signals are GLOBAL LABELS
and the rails are the same power:+3.3V / power:GND symbols the partners' sheet uses, so the
sheets join the partners' analog sheet by name. Designators: POWER 1xx, MCU 2xx, PHOTODIODE 3xx.
The netlist these implement is design/*.circuit.json (checked there first).
"""
from pathlib import Path

from ksch import Sheet

PROJECT = "SSVEP_PCB"
ROOT_UUID = "24208f67-7b82-44aa-b72f-6dc83391700a"          # the partners' root sheet
SHEET_UUID = {"power": "5f0c3a5e-1d6b-4f1e-9b7a-3c2e8d4a1001",
              "mcu": "5f0c3a5e-1d6b-4f1e-9b7a-3c2e8d4a1002",
              "photodiode": "5f0c3a5e-1d6b-4f1e-9b7a-3c2e8d4a1003"}
OUT = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB/sheets")
DATE = "2026-10-19"

R_FP = "Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"
C_FP = "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"
R_DS = "https://yageogroup.com/content/Resource%20Library/Datasheet/PYU-RC_GROUP_51_ROHS_L.pdf"
C_DS = {"CL21B104KBCNNNC": "https://product.samsungsem.com/mlcc/CL21B104KBCNNN.do",
        "CL21B105KAFNNNE": "https://product.samsungsem.com/mlcc/CL21B105KAFNNN.do",
        "CL21C103JBF1PNE": "https://product.samsungsem.com/mlcc/CL21C103JBF1PN.do"}
R_MPN = {"0": "RC0805JR-070RL", "33": "RC0805FR-0733RL", "1k": "RC0805FR-071KL", "10k": "RC0805FR-0710KL", "100k": "RC0805FR-07100KL"}
TP_FP = "TestPoint:TestPoint_Keystone_5015_Micro_Mini"
TP_DS = "https://www.keyelco.com/userAssets/file/M65p55.pdf"
P33, GND = "power:+3.3V", "power:GND"


def sheet(name, title, page, comments=()):
    return Sheet(title, PROJECT, ROOT_UUID, SHEET_UUID[name], page=page, date=DATE, rev="A",
                 company="SSVEP EEG board", comments=comments)


def res_h(s, ref, value, x, y, dnp=False):
    """A resistor lying horizontally, pin 1 on the left. Returns (left pin, right pin)."""
    s.place(ref, "Device:R", x, y, rot=90, value=value, footprint=R_FP, datasheet=R_DS,
            mpn=R_MPN[value], dnp=dnp, ref_at=(x - 3.81, y - 1.905), val_at=(x + 1.27, y - 1.905),
            field_angle=90)
    return s.pin(ref, "1"), s.pin(ref, "2")


def res_v(s, ref, value, x, y):
    s.place(ref, "Device:R", x, y, value=value, footprint=R_FP, datasheet=R_DS, mpn=R_MPN[value],
            ref_at=(x + 2.032, y - 0.635), val_at=(x + 2.032, y + 1.905))
    return s.pin(ref, "1"), s.pin(ref, "2")          # top, bottom


def cap_v(s, ref, value, mpn, x, y, dnp=False):
    s.place(ref, "Device:C", x, y, value=value, footprint=C_FP, datasheet=C_DS[mpn], mpn=mpn,
            dnp=dnp, ref_at=(x + 2.54, y - 0.635), val_at=(x + 2.54, y + 1.905))
    return s.pin(ref, "1"), s.pin(ref, "2")          # top, bottom


def gnd_below(s, p, drop=2.54):
    q = (p[0], p[1] + drop)
    s.wire(p, q)
    s.power(GND, q)


def p33_above(s, p, rise=2.54):
    q = (p[0], p[1] - rise)
    s.wire(p, q)
    s.power(P33, q)


# =====================================================================================  POWER
# Real parts use the house symbols in libs/SSVEP.kicad_sym (gen_symbols.py, from design/parts);
# passives and rails use Device:/power: like the partners' sheet.
def power():
    s = sheet("power", "Power: 1S LiPo, switch, low-noise analog 3.3 V", "2",
              ("Cell -> F101 -> Q101 -> SW101 -> VBAT (MCU) and U101 -> +3.3V (analog)",
               "No switching regulator: LP5907, 10 uVrms",
               "U101 off until the MCU drives ANA_EN high"))
    s.text("POWER", (25.4, 30.48), size=2.54, bold=True)
    s.text("1S protected LiPo (JST PH). CHECK PACK POLARITY: vendors disagree on which pin is +.\n"
           "F101 + Q101: a short trips the fuse; a reversed pack leaves Q101 off (its body diode blocks).\n"
           "Q101 is fully on either way current flows, so the XIAO still charges the cell through it.\n"
           "SW101 is the main switch: off disconnects everything, including charging through the XIAO.\n"
           "U101 makes the partners' +3.3V analog rail straight from the cell (holds 3.3 V down to ~3.35 V).",
           (25.4, 48.26))

    # battery, mirrored so its pins face the circuit
    s.place("J101", "SSVEP:B2B-PH-K-S", 33.02, 77.47, mirror="y", value="BATT 1S",
            footprint="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
            datasheet="https://www.jst-mfg.com/product/pdf/eng/ePH.pdf", mpn="B2B-PH-K-S",
            ref_at=(20.32, 71.12), val_at=(20.32, 73.66))
    bat_p, bat_n = s.pin("J101", "1"), s.pin("J101", "2")          # (48.26, 76.2), (48.26, 78.74)
    s.wire(bat_n, (53.34, bat_n[1]), (53.34, 88.9))
    s.power(GND, (53.34, 88.9))
    s.wire((53.34, 86.36), (58.42, 86.36))
    s.junction((53.34, 86.36))
    s.power("power:PWR_FLAG", (58.42, 86.36), rot=180)

    # cell protection, in the + lead before the switch: fuse, then reverse-battery P-FET (drain to
    # the cell, source to the load, gate to GND). Correct pack: the body diode lifts the source, Vgs
    # = -Vcell and the FET turns fully on. Reversed pack: drain goes negative, the gate sits at 0 V
    # and the body diode is reverse-biased, so nothing downstream ever sees the reversed cell.
    s.place("F101", "SSVEP:Fuse", 58.42, bat_p[1], rot=90, value="500mA",
            footprint="Fuse:Fuse_1206_3216Metric",
            datasheet="https://www.littelfuse.com/assetdocs/fuse-466-datasheet?assetguid=dbe9bcd7-6072-4adf-bf5b-d33e52a6b90f",
            mpn="0466.500NR", fields={"Manufacturer": "Littelfuse", "DigiKey_PN": "F1454CT-ND"},
            ref_at=(54.61, 71.12), val_at=(54.61, 73.66), field_angle=90)
    f1, f2 = s.pin("F101", "1"), s.pin("F101", "2")
    s.wire(bat_p, f1)
    s.place("Q101", "SSVEP:Q_PMOS", 76.2, bat_p[1] + 2.54, rot=90, value="SI2301CDS",
            footprint="Package_TO_SOT_SMD:SOT-23", datasheet="https://www.vishay.com/docs/68741/si2301cd.pdf",
            mpn="SI2301CDS-T1-BE3",
            fields={"Manufacturer": "Vishay Siliconix", "DigiKey_PN": "742-SI2301CDS-T1-BE3CT-ND"},
            ref_at=(78.74, 83.82), val_at=(78.74, 86.36), field_angle=90)
    qg, qs, qd = s.pin("Q101", "1"), s.pin("Q101", "2"), s.pin("Q101", "3")
    s.wire(f2, qd)
    gnd_below(s, qg)

    s.place("SW101", "SSVEP:EG1218", 106.68, 76.2, value="EG1218",
            footprint="SSVEP:SW_Slide_SPDT_EG1218",
            datasheet="https://configured-product-images.s3.amazonaws.com/Datasheets/EG.pdf",
            mpn="EG1218", ref_at=(93.98, 69.85), val_at=(93.98, 83.82))
    com, a, b = s.pin("SW101", "2"), s.pin("SW101", "1"), s.pin("SW101", "3")
    s.wire(qs, com)
    s.nc(b)

    # VBAT row (switch -> VBAT global label + PWR_FLAG -> R101); R101 or R102 -> LDO_IN -> C101 -> U101.IN
    s.place("U101", "SSVEP:LP5907MFX-3.3", 170.18, 81.28, value="LP5907MFX-3.3",
            footprint="Package_TO_SOT_SMD:SOT-23-5", datasheet="https://www.ti.com/lit/gpn/lp5907",
            mpn="LP5907MFX-3.3/NOPB", fields={"Manufacturer": "Texas Instruments", "DigiKey_PN": "296-38557-1-ND"}, ref_at=(157.48, 64.77), val_at=(157.48, 67.31))
    vin, en, ncp, gnd, vout = (s.pin("U101", n) for n in ("1", "3", "4", "2", "5"))
    yv = vin[1]
    # source select: two 0 ohm links stacked on one column, meeting at the LDO_IN node between them.
    # R101 (fitted) comes up from the VBAT row; R102 (not fitted) comes down from VBUS.
    jx = 137.16
    for ref, y, dnp in (("R101", yv + 3.81, False), ("R102", yv - 3.81, True)):
        s.place(ref, "Device:R", jx, y, value="0", footprint=R_FP, datasheet=R_DS, mpn=R_MPN["0"],
                dnp=dnp, ref_at=(jx - 5.715, y - 0.635), val_at=(jx - 5.715, y + 1.905))
    ja, jb = s.pin("R101", "2"), s.pin("R102", "1")                 # VBAT end, VBUS end
    yb = ja[1]
    rx, gx = a[0] + 2.54, 127.0
    s.wire(a, (rx, a[1]), (rx, yb), (gx, yb), ja)                    # throw A drops onto the VBAT row
    s.junction((gx, yb))
    s.wire((gx, yb), (gx, 63.5))
    s.glabel("VBAT", (gx, 63.5), angle=90, shape="output")
    s.wire((gx, 66.04), (116.84, 66.04))
    s.junction((gx, 66.04))
    s.power("power:PWR_FLAG", (116.84, 66.04))
    s.wire(jb, (jb[0], 63.5))
    s.glabel("VBUS", (jb[0], 63.5), angle=90, shape="input")
    cx, fx = 146.05, 149.86
    s.wire((jx, yv), (cx, yv), (fx, yv), vin)
    s.junction((jx, yv)); s.junction((cx, yv)); s.junction((fx, yv))
    s.label("LDO_IN", (jx + 1.27, yv))
    # fed through a link (passive), so tell ERC this net is supplied
    s.wire((fx, yv), (fx, yv - 3.81))
    s.power("power:PWR_FLAG", (fx, yv - 3.81))
    c_top, c_bot = cap_v(s, "C101", "1u", "CL21B105KAFNNNE", cx, yv + 3.81)
    gnd_below(s, c_bot)
    # pin 4 is typed no_connect in the generated symbol: no flag needed
    s.power(GND, gnd)
    s.wire(en, (151.13, en[1]), (151.13, 99.06), (144.78, 99.06))
    s.glabel("ANA_EN", (144.78, 99.06), angle=180, shape="input")
    s.text("R101 / R102 pick the analog LDO's input (fit exactly one).\n"
           "Default, R101 fitted: the switched cell (VBAT).\n"
           "Move the 0 ohm to R102: USB 5 V from the XIAO, so the\n"
           "analog side runs with no cell. BENCH TESTING ONLY:\n"
           "the electrodes then share the PC's ground via USB.", (101.6, 121.92))

    # +3.3V out
    yo = vout[1]
    c2x, railx = 193.04, 200.66
    s.wire(vout, (c2x, yo), (railx, yo))
    s.junction((c2x, yo))
    c_top, c_bot = cap_v(s, "C102", "1u", "CL21B105KAFNNNE", c2x, yo + 3.81)
    gnd_below(s, c_bot)
    s.power(P33, (railx, yo))

    # test points
    s.box(205.74, 55.88, 271.78, 106.68)
    s.text("Test points", (208.28, 59.69), bold=True)
    for ref, val, y in (("TP101", "VBAT", 68.58), ("TP102", "+3.3V", 81.28), ("TP103", "GND", 93.98)):
        s.place(ref, "SSVEP:5015", 243.84, y, value=val, footprint=TP_FP, datasheet=TP_DS, mpn="5015",
                ref_at=(233.68, y - 3.81), val_at=(246.38, y - 3.81))
        p = s.pin(ref, "1")
        q = (p[0] - 5.08, p[1])
        s.wire(p, q)
        if val == "VBAT":
            s.glabel("VBAT", q, angle=180, shape="input")
        elif val == "+3.3V":
            p33_above(s, q)
        else:
            gnd_below(s, q)

    # mounting holes: unplated, so no screw or standoff ties the electrodes' ground to anything
    s.text("Mounting holes (M3, unplated, one per board corner)", (208.28, 115.57), bold=True)
    for i, x in enumerate((215.9, 228.6, 241.3, 254.0), 1):
        s.place(f"H10{i}", "Mechanical:MountingHole", x, 121.92, value="M3",
                footprint="MountingHole:MountingHole_3.2mm_M3", in_bom=False)

    s.text("+3.3V feeds the partners' analog sheet (INA333 x4, MCP6002, ADS131M08):\n"
           "11.5 mA worst case of the LP5907's 250 mA (design/power_budget.json).",
           (101.6, 137.16))
    s.write(OUT / "power.kicad_sch")


# =====================================================================================  MCU
def mcu():
    s = sheet("mcu", "MCU: Seeed XIAO nRF52840, SPI to the ADS131M08", "3",
              ("D8 SCLK, D10 MOSI, D9 MISO, D7 CS, D6 DRDY",
               "D5 SYNC/RST, D4 ANA_EN, D3 CLKIN; D0-D2 spare",
               "FW: ADC pins low/high-Z before ANA_EN goes low"))
    s.text("MCU", (25.4, 30.48), size=2.54, bold=True)

    X, Y = 88.9, 88.9
    s.place("U201", "SSVEP:XIAO-nRF52840", X, Y, value="XIAO nRF52840",
            footprint="SSVEP:XIAO-nRF52840-SMD_VBAT-hole", datasheet="https://wiki.seeedstudio.com/XIAO_BLE/",
            mpn="102010448", ref_at=(76.2, 58.42), val_at=(76.2, 60.96))
    p = lambda n: s.pin("U201", n)
    for n in ("1", "2", "3", "12", "15", "16", "17", "21", "22"):
        s.nc(p(n))
    lx = 66.04                                    # left stub ends
    v = p("19"); s.wire(v, (lx, v[1])); s.label("VBAT_XIAO", (lx, v[1]), angle=180)
    u = p("14"); s.wire(u, (lx, u[1])); s.glabel("VBUS", (lx, u[1]), angle=180, shape="output")
    for n, kind, name, shape in (("4", "l", "MCU_CLK", None), ("5", "g", "ANA_EN", "output"),
                                 ("6", "g", "ADC_SYNC_RST", "output"), ("7", "g", "ADC_DRDY_N", "input")):
        a = p(n)
        s.wire(a, (lx, a[1]))
        if kind == "l":
            s.label(name, (lx, a[1]), angle=180)
        else:
            s.glabel(name, (lx, a[1]), angle=180, shape=shape)
    g = p("13")                                   # pads 13, 18, 20 are one stacked GND pin
    s.wire(g, (68.58, g[1]), (68.58, g[1] + 2.54))
    s.power(GND, (68.58, g[1] + 2.54))
    for n, name in (("8", "MCU_CS"), ("9", "MCU_SCLK"), ("10", "MCU_MISO"), ("11", "MCU_MOSI")):
        a = p(n)
        s.wire(a, (a[0] + 5.08, a[1]))
        s.label(name, (a[0] + 5.08, a[1]))
    s.text("U201 is soldered by its castellated edge pads. Only VBAT (pad 19)\n"
           "is underneath: solder it through the plated hole from the back.\n"
           "GND is pads 13 (edge), 18 and 20 (underneath) stacked.", (55.88, 124.46))

    # ---- SPI series resistors (33 ohm at the XIAO)
    s.box(124.46, 55.88, 190.5, 101.6)
    s.text("SPI to ADS131M08 (33 R series)", (127.0, 59.69), bold=True)
    for ref, local, glob, shape, y in (("R201", "MCU_SCLK", "ADC_SCLK", "output", 67.31),
                                       ("R202", "MCU_MOSI", "ADC_DIN", "output", 74.93),
                                       ("R204", "MCU_MISO", "ADC_DOUT", "input", 82.55),
                                       ("R203", "MCU_CS", "ADC_CS_N", "output", 90.17)):
        l, r = res_h(s, ref, "33", 152.4, y)
        s.wire((140.97, y), l)
        s.label(local, (140.97, y), angle=180)
        s.wire(r, (167.64, y))
        s.glabel(glob, (167.64, y), shape=shape)

    # ---- ADC master clock
    s.box(17.78, 132.08, 116.84, 172.72)
    s.text("ADC master clock", (20.32, 135.89), bold=True)
    y = 142.24
    l, r = res_h(s, "R205", "33", 45.72, y)
    s.wire((35.56, y), l)
    s.label("MCU_CLK", (35.56, y), angle=180)
    node = (83.82, y)
    s.wire(r, node, (91.44, y))
    s.junction(node)
    s.glabel("ADC_CLKIN", (91.44, y), shape="output")
    s.place("Y201", "SSVEP:ECS-2520MVLC-081.92-CN-TR", 55.88, 160.02, value="8.192MHz",
            footprint="Oscillator:Oscillator_SMD_ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm",
            datasheet="https://ecsxtal.com/store/pdf/ECS-2520MVLC.pdf", mpn="ECS-2520MVLC-081.92-CN-TR",
            dnp=True, ref_at=(45.72, 148.59), val_at=(55.88, 148.59))
    vdd, ts, yg, out = (s.pin("Y201", n) for n in ("4", "1", "2", "3"))
    s.wire(vdd, (35.56, vdd[1]))
    s.wire(ts, (35.56, ts[1]), (35.56, vdd[1]), (35.56, vdd[1] - 2.54))
    s.junction((35.56, vdd[1]))
    s.power(P33, (35.56, vdd[1] - 2.54))
    s.wire(yg, (38.1, yg[1]), (38.1, yg[1] + 2.54))
    s.power(GND, (38.1, yg[1] + 2.54))
    l6, r6 = res_h(s, "R206", "33", 78.74, out[1], dnp=True)
    s.wire(out, l6)
    s.wire(r6, (node[0], r6[1]), node)
    c_top, c_bot = cap_v(s, "C201", "100n", "CL21B104KBCNNNC", 25.4, 160.02, dnp=True)
    p33_above(s, c_top)
    gnd_below(s, c_bot)
    s.text("Default: the XIAO drives CLKIN\nat 8 MHz through R205.\n"
           "Exact 8.192 MHz: fit Y201, C201,\nR206 and remove R205.", (88.9, 157.48))

    # ---- SYNC/RESET pull-up
    s.box(124.46, 106.68, 190.5, 134.62)
    s.text("ADC SYNC/RESET pull-up", (127.0, 110.49), bold=True)
    top, bot = res_v(s, "R207", "10k", 175.26, 121.92)
    p33_above(s, top)
    s.wire(bot, (175.26, 129.54), (162.56, 129.54))
    s.glabel("ADC_SYNC_RST", (162.56, 129.54), angle=180, shape="input")
    s.text("Keeps the ADC out of reset while\nthe XIAO's pins float at boot.", (127.0, 118.11))

    # ---- charge link and XIAO VBAT decoupling
    s.box(124.46, 139.7, 193.04, 165.1)
    s.text("Charge link (remove R208 to isolate the XIAO charger)", (127.0, 143.51), bold=True)
    y = 153.67
    s.glabel("VBAT", (129.54, y), angle=180, shape="input")
    ja, jb = res_h(s, "R208", "0", 149.86, y)
    s.wire((129.54, y), ja)
    cx = 172.72
    s.wire(jb, (cx, y), (182.88, y))
    s.junction((cx, y))
    s.label("VBAT_XIAO", (jb[0] + 2.54, y))
    # fed through the link (passive), so tell ERC this net is supplied
    s.wire((182.88, y), (182.88, 156.21))
    s.power("power:PWR_FLAG", (182.88, 156.21), rot=180)
    c_top, c_bot = cap_v(s, "C202", "1u", "CL21B105KAFNNNE", cx, y + 3.81)
    gnd_below(s, c_bot, drop=1.27)
    s.write(OUT / "mcu.kicad_sch")


# =====================================================================================  PHOTODIODE
def photodiode():
    s = sheet("photodiode", "Photodiode: screen-sync input to ADC channel 4", "4",
              ("BPW34 on a cable, taped over a screen sync patch",
               "PD_OUT -> ADS131M08 AIN4P, sampled with the EEG",
               "Keep white under +1.2 V: lower R303 if bright"))
    s.text("PHOTODIODE (screen sync)", (25.4, 30.48), size=2.54, bold=True)
    s.place("J301", "SSVEP:B2B-PH-K-S", 38.1, 77.47, mirror="y", value="SYNC_CABLE",
            footprint="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
            datasheet="https://www.jst-mfg.com/product/pdf/eng/ePH.pdf", mpn="B2B-PH-K-S",
            ref_at=(25.4, 71.12), val_at=(25.4, 73.66))
    k, a = s.pin("J301", "1"), s.pin("J301", "2")                    # (53.34, 76.2), (53.34, 78.74)
    s.text("J301: 2-pin cable to the BPW34 photodiode taped to the screen\n"
           "pin 1 = photodiode cathode (PD_BIAS), pin 2 = anode (PD_SIG)", (25.4, 109.22))
    bx, cx = 76.2, 86.36
    s.wire(k, (bx, k[1]), (cx, k[1]))
    s.junction((bx, k[1]))
    s.label("PD_BIAS", (58.42, k[1]))
    top, bot = res_v(s, "R301", "1k", bx, k[1] - 3.81)
    p33_above(s, top)
    c_top, c_bot = cap_v(s, "C301", "100n", "CL21B104KBCNNNC", cx, k[1] + 3.81)
    gnd_below(s, c_bot)
    y = 99.06
    s.wire(a, (63.5, a[1]), (63.5, y))
    s.label("PD_SIG", (55.88, a[1]))
    l, r = res_h(s, "R302", "1k", 72.39, y)
    s.wire((63.5, y), l)
    x3, x4, xo = 86.36, 96.52, 109.22
    s.wire(r, (x3, y), (x4, y), (xo, y))
    s.junction((x3, y)); s.junction((x4, y))
    t3, b3 = res_v(s, "R303", "100k", x3, y + 3.81)
    gnd_below(s, b3)
    t4, b4 = cap_v(s, "C302", "10n", "CL21C103JBF1PNE", x4, y + 3.81)
    gnd_below(s, b4)
    s.glabel("PD_OUT", (xo, y), shape="output")
    s.text("R303 + C302: photocurrent to voltage with ~1 ms smoothing (backlight PWM).\n"
           "~10 uA from a white patch -> ~1 V into the ADC.", (25.4, 142.24))
    s.write(OUT / "photodiode.kicad_sch")


if __name__ == "__main__":
    power()
    mcu()
    photodiode()
    print("wrote", sorted(p.name for p in OUT.glob("*.kicad_sch")))
