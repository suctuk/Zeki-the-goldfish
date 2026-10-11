# hw.py — board init for Zeki (SparkFun Thing Plus ESP32 WROOM USB-C, WRL-20168)
#
# Qwiic power is switched by GPIO0. It must be driven HIGH before I2C init,
# or the whole Qwiic chain is unpowered and the scan comes back empty.
#
# One shared bus: SparkFun's qwiic_i2c driver owns the machine.I2C on 21/22.
# Pass qwiic() to every SparkFun driver (i2c_driver=...), and i2c() to
# anything that wants a raw machine.I2C (ssd1306, scans).

import time
from machine import Pin
import qwiic_i2c

QWIIC_PWR_PIN = 0
SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 400_000

ADDR_TOF = 0x29
ADDR_BUZZER = 0x34
ADDR_FUEL = 0x36
ADDR_OLED = 0x3D
ADDR_TWIST = 0x3F

KNOWN = {
    ADDR_TOF: "VL53L1X distance",
    ADDR_BUZZER: "Qwiic Buzzer",
    ADDR_FUEL: "MAX17048 fuel gauge (onboard)",
    ADDR_OLED: "OLED 1.3in (SSD1306)",
    ADDR_TWIST: "Qwiic Twist",
}

_qwiic = None


def qwiic_power(on=True):
    Pin(QWIIC_PWR_PIN, Pin.OUT, value=1 if on else 0)


def qwiic():
    """Power the Qwiic chain and return the shared SparkFun I2C driver."""
    global _qwiic
    if _qwiic is None:
        qwiic_power(True)
        time.sleep_ms(100)
        _qwiic = qwiic_i2c.getI2CDriver(sda=SDA_PIN, scl=SCL_PIN, freq=I2C_FREQ)
    return _qwiic


def i2c():
    """The raw machine.I2C under the shared driver."""
    return qwiic().i2cbus


def scan():
    found = i2c().scan()
    print("I2C scan: {} device(s)".format(len(found)))
    for addr in found:
        print("  0x{:02X}  {}".format(addr, KNOWN.get(addr, "?")))
    return found


def oled():
    import ssd1306
    return ssd1306.SSD1306_I2C(128, 64, i2c(), addr=ADDR_OLED)


def tof():
    import qwiic_vl53l1x
    s = qwiic_vl53l1x.QwiicVL53L1X(ADDR_TOF, i2c_driver=qwiic())
    err = s.sensor_init()  # None/0 on success, nonzero error code on failure
    if err:
        raise OSError("VL53L1X init failed: {}".format(err))
    return s


def twist():
    import qwiic_twist
    t = qwiic_twist.QwiicTwist(ADDR_TWIST, i2c_driver=qwiic())
    if not t.begin():
        raise OSError("Qwiic Twist not found")
    return t


def buzzer():
    import qwiic_buzzer
    b = qwiic_buzzer.QwiicBuzzer(ADDR_BUZZER, i2c_driver=qwiic())
    if not b.begin():
        raise OSError("Qwiic Buzzer not found")
    return b


if __name__ == "__main__":
    scan()
