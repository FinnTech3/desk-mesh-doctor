#!/usr/bin/env python3
"""finish.py SRC.png DST.png [MAX_WIDTH] [COLOURS]: shrink a real PNG for the repo (palette PNG, optional downscale).
Nothing is added to the picture; only the colour count and, if asked, the size change. COLOURS 0 keeps full colour."""
import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
if len(sys.argv) > 3 and int(sys.argv[3]) and im.width > int(sys.argv[3]):
    im = im.resize((int(sys.argv[3]), round(im.height * int(sys.argv[3]) / im.width)), Image.LANCZOS)
colours = int(sys.argv[4]) if len(sys.argv) > 4 else 128
if colours:
    im = im.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
im.save(dst, optimize=True)
