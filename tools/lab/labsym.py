import re
_B = r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\build"
def lo(n):
    s = open(_B + r"\lo_syms.inc").read()
    return int(re.search(r"^LO_" + n + r"\s+equ\s+(\S+)", s, re.M).group(1), 0)
def hi(n):
    s = open(_B + r"\rosetta_hi.map").read()
    return int(re.search(r"^\s*([0-9A-F]+)\s+[0-9A-F]+\s+" + n + r"\s*$", s, re.M).group(1), 16)
