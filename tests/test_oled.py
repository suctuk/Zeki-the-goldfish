# OLED: print "hi, I'm Zeki"
import hw

d = hw.oled()
d.fill(0)
d.text("hi, I'm Zeki", 16, 28, 1)
d.show()
print("OLED: drew \"hi, I'm Zeki\"")
