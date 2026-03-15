"""
Generate ECGViewer.ico — medical ECG monitor icon
Design: dark navy background, phosphor-green ECG trace (PQRST morphology)
"""
import os
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))

def draw_icon(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── rounded square background (dark navy) ──────────────────────────────
    r = max(2, s // 5)
    d.rounded_rectangle([0, 0, s-1, s-1], radius=r, fill=(14, 22, 42, 255))

    # ── subtle ECG grid (only visible at larger sizes) ─────────────────────
    if s >= 48:
        gc = (0, 70, 35, 50)
        step = s // 8
        for i in range(1, 8):
            d.line([(i*step, r), (i*step, s-r)], fill=gc, width=1)
            d.line([(r, i*step), (s-r, i*step)], fill=gc, width=1)

    # ── ECG trace: PQRST waveform ──────────────────────────────────────────
    base_y  = 0.58
    pad_x   = 0.09
    x_range = 1.0 - 2 * pad_x

    waypoints = [
        (0.00,  0.00),   # flat entry
        (0.14,  0.00),   # approach P
        (0.20, -0.10),   # P wave peak
        (0.26,  0.00),   # P wave end / PR segment
        (0.33,  0.04),   # Q dip
        (0.39, -0.65),   # R peak (dominant spike)
        (0.44,  0.20),   # S trough
        (0.49,  0.00),   # ST segment start
        (0.54,  0.00),   # ST segment end
        (0.61, -0.15),   # T wave peak
        (0.70,  0.00),   # T wave end
        (1.00,  0.00),   # flat exit
    ]

    pts = [
        ((pad_x + xf * x_range) * s,
         (base_y + yf * 0.40) * s)
        for xf, yf in waypoints
    ]

    # Glow pass (wider, transparent)
    gw = max(4, s // 12)
    d.line(pts, fill=(0, 210, 70, 45), width=gw)

    # Main trace (phosphor green)
    lw = max(1, s // 20)
    d.line(pts, fill=(0, 228, 66, 255), width=lw)

    # ── bright dot at R-peak ───────────────────────────────────────────────
    if s >= 24:
        rx, ry = pts[5]
        dr = max(2, s // 32)
        d.ellipse([rx-dr, ry-dr, rx+dr, ry+dr], fill=(160, 255, 140, 255))

    # ── border: subtle green rim ───────────────────────────────────────────
    bw = max(1, s // 64)
    d.rounded_rectangle([bw, bw, s-1-bw, s-1-bw],
                         radius=r, outline=(0, 140, 55, 110), width=bw)

    return img


def main():
    # Save preview PNG (256px) for inspection
    img256 = draw_icon(256)
    png_path = os.path.join(BASE, "ecgviewer_256.png")
    img256.save(png_path)
    print("Preview:", png_path)

    # Build ICO: draw each size independently (sharp at every resolution),
    # then write a proper multi-image ICO using raw ICO format assembly.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_icon(sz) for sz in sizes]

    # Save each as temp PNG, then bundle into ICO via Pillow's ICO plugin
    # The correct Pillow API: save with sizes= on the LARGEST image;
    # Pillow will downscale. But since we drew each size sharply ourselves,
    # we assemble the ICO binary manually.
    import struct, io

    def png_bytes(img):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    entries = [(sz, png_bytes(img)) for sz, img in zip(sizes, images)]

    # ICO format:
    #   6-byte header: reserved(2) type(2)=1 count(2)
    #   per entry: width(1) height(1) colors(1) reserved(1) planes(2) bpp(2) size(4) offset(4)
    #   then raw PNG data for each entry
    n = len(entries)
    header_size = 6 + n * 16
    offsets = []
    off = header_size
    for _, data in entries:
        offsets.append(off)
        off += len(data)

    ico = io.BytesIO()
    ico.write(struct.pack("<HHH", 0, 1, n))      # file header
    for i, (sz, data) in enumerate(entries):
        w = h = sz if sz < 256 else 0            # 0 means 256 in ICO spec
        ico.write(struct.pack("<BBBBHHII",
                              w, h,              # width, height
                              0,                 # color count (0 = no palette)
                              0,                 # reserved
                              1,                 # planes
                              32,                # bits per pixel
                              len(data),         # image data size
                              offsets[i]))       # offset to image data
    for _, data in entries:
        ico.write(data)

    ico_path = os.path.join(BASE, "ecgviewer.ico")
    with open(ico_path, "wb") as f:
        f.write(ico.getvalue())

    kb = os.path.getsize(ico_path) / 1024
    print("Icon:   ", ico_path)
    print("Sizes:  ", sizes)
    print("File:   ", f"{kb:.1f} KB")


if __name__ == "__main__":
    main()
