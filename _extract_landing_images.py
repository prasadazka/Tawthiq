"""Extract the 4 base64-embedded images from svg.txt and write them as PNGs
into frontend/public/landing/. Also print the positions where the figma
references them via <use> so we can place them in the React landing."""
import base64
import re
from pathlib import Path

SVG = Path("svg.txt").read_text(encoding="utf-8")
OUT_DIR = Path("frontend/public/landing")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# <image id="image0_1_2" width="1024" height="1024" preserveAspectRatio="none" xlink:href="data:image/png;base64,XXXX"/>
img_pattern = re.compile(
    r'<image\s+id="(image\d+_\d+_\d+)"\s+width="(\d+)"\s+height="(\d+)"[^>]*xlink:href="data:image/(png|jpeg|jpg);base64,([^"]+)"',
    re.DOTALL,
)

for m in img_pattern.finditer(SVG):
    img_id = m.group(1)
    w = m.group(2)
    h = m.group(3)
    ext = m.group(4)
    b64 = m.group(5)
    # Clean whitespace just in case
    clean = re.sub(r"\s+", "", b64)
    blob = base64.b64decode(clean)
    out = OUT_DIR / f"{img_id}.{ext}"
    out.write_bytes(blob)
    print(f"  → {out}  {w}×{h}  {len(blob):,} bytes")

# Also dump the <use> calls that position each image
use_pattern = re.compile(
    r'<use\s+xlink:href="#(image\d+_\d+_\d+)"\s+transform="([^"]+)"',
)
print("\nPositioning (transform applied per image):")
for m in use_pattern.finditer(SVG):
    print(f"  {m.group(1):<15} transform=\"{m.group(2)}\"")
