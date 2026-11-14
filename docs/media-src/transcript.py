#!/usr/bin/env python3
"""transcript.py CAST.json OUT.txt: write the recorded session as plain text (notes, "$ command", real output, unwrapped)."""
import json
import sys

cast = json.load(open(sys.argv[1]))
out = []
for st in cast["steps"]:
    if st["type"] == "note":
        out.append(st["text"])
    elif st["type"] == "cmd":
        out.append("$ " + st["text"])
    elif st["type"] == "out":
        out.append(st.get("raw", st["text"]))
open(sys.argv[2], "w").write("\n".join(out) + "\n")
