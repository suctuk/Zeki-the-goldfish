# Qwiic Buzzer: short 3-note rising chime (C7 E7 G7)
#
# The transducer resonates at 2730 Hz. Notes far below that (e.g. C5-G5) are
# inaudible, so Zeki's chimes live in the C7-G7 band. There, VOLUME_MID is
# audible but public-friendly; MIN/LOW are too quiet; MAX is very loud.
import time
import hw

b = hw.buzzer()
print("Buzzer fw v{}.{}".format(b.firware_version_major(), b.firware_version_minor()))
for note in (b.NOTE_C7, b.NOTE_E7, b.NOTE_G7):
    b.configure(note, 120, b.VOLUME_MID)
    b.on()
    time.sleep_ms(140)
b.off()
print("Buzzer: chime played")
