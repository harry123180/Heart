import ctypes, ctypes.wintypes, time, sys, psutil
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Find ECGViewer HWND
target_pid = None
for proc in psutil.process_iter(['name', 'pid']):
    if proc.info['name'] == 'ECGViewer.exe':
        target_pid = proc.info['pid']
        break

if not target_pid:
    print("ECGViewer not running"); sys.exit(1)

results = []
def enum_cb(h, _):
    pid = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value == target_pid and ctypes.windll.user32.IsWindowVisible(h):
        results.append(h)
    return True
ctypes.windll.user32.EnumWindows(
    ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(enum_cb), 0)

if not results:
    print("No visible window"); sys.exit(1)
hwnd = results[0]

# Restore window
ctypes.windll.user32.ShowWindow(hwnd, 9)
time.sleep(0.5)

# Get window rect
class RECT(ctypes.Structure):
    _fields_ = [('left',ctypes.c_long),('top',ctypes.c_long),
                ('right',ctypes.c_long),('bottom',ctypes.c_long)]
r = RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
w = r.right - r.left
h = r.bottom - r.top
print(f"Window {w}x{h} at ({r.left},{r.top})")

# PrintWindow: renders window into a DC regardless of z-order
import ctypes.wintypes as wt

gdi32  = ctypes.windll.gdi32
user32 = ctypes.windll.user32

# Create compatible DC and bitmap
hdc_screen = user32.GetDC(0)
hdc_mem    = gdi32.CreateCompatibleDC(hdc_screen)
hbmp       = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
gdi32.SelectObject(hdc_mem, hbmp)

# PW_RENDERFULLCONTENT = 2 (works for hardware-accelerated Qt windows)
result = user32.PrintWindow(hwnd, hdc_mem, 2)
print(f"PrintWindow result: {result}")

# Read bitmap pixels via GetDIBits
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize',wt.DWORD),('biWidth',ctypes.c_long),
                ('biHeight',ctypes.c_long),('biPlanes',wt.WORD),
                ('biBitCount',wt.WORD),('biCompression',wt.DWORD),
                ('biSizeImage',wt.DWORD),('biXPelsPerMeter',ctypes.c_long),
                ('biYPelsPerMeter',ctypes.c_long),('biClrUsed',wt.DWORD),
                ('biClrImportant',wt.DWORD)]

bih = BITMAPINFOHEADER()
bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bih.biWidth = w
bih.biHeight = -h   # negative = top-down
bih.biPlanes = 1
bih.biBitCount = 32
bih.biCompression = 0  # BI_RGB

buf_size = w * h * 4
buf = (ctypes.c_byte * buf_size)()
gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bih), 0)

# Cleanup GDI
gdi32.DeleteObject(hbmp)
gdi32.DeleteDC(hdc_mem)
user32.ReleaseDC(0, hdc_screen)

# Convert BGRA buffer to PNG via PIL
import numpy as np
from PIL import Image
arr = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
# GDI gives BGRA, PIL needs RGBA
arr = arr[:, :, [2, 1, 0, 3]]
img = Image.fromarray(arr, 'RGBA').convert('RGB')
out = r'C:\Users\TSIC\Documents\GitHub\Heart\output\ecgviewer_window.png'
img.save(out)
print(f"Saved: {out}")
