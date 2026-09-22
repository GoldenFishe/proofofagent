#!/usr/bin/env python3
"""Record a live ProofOfAgent e2e.sh run (PTY) -> terminal mp4 + transcript.
Renders the terminal with pyte; exports PNG frames; narration added later."""
import os, pty, time, select, subprocess, fcntl, struct, termios
import pyte
from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 96, 40
CW, CH = 10, 22
W, H = COLS*CW, 30 + ROWS*CH
BG = (13, 17, 23)
FG = (230, 237, 245)
DIM = (139, 148, 158)
ACCENT = (52, 211, 153)
FONT = "/usr/share/fonts/truetype/freefont/FreeMono.ttf"
FBOLD = "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf"
fnt = ImageFont.truetype(FONT, 17)
fntb = ImageFont.truetype(FBOLD, 17)

OUT = "/karl/proofofagent/live_demo"
os.makedirs(OUT + "/frames", exist_ok=True)

env = dict(os.environ)
env["PATH"] = "/home/karl/.local/share/solana/install/active_release/bin:" + \
              "/home/karl/.cargo/bin:" + env.get("PATH", "")
script = "bash /karl/proofofagent/e2e.sh"

pid, fd = pty.fork()
if pid == 0:
    os.execvpe("bash", ["bash", "-c", script], env)
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

screen = pyte.Screen(COLS, ROWS)
stream = pyte.Stream(screen)

frames = []
transcript = []
t0 = time.time()
done = False
MAX = 150
last_render = 0.0
while time.time() - t0 < MAX and not done:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try:
            data = os.read(fd, 65536)
        except OSError:
            data = b""
        if not data:
            done = True
            break
        stream.feed(data.decode("utf-8", "replace"))
    # render at ~6 fps
    now = time.time()
    if now - last_render >= 1/6:
        last_render = now
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 30], fill=(30, 41, 59))
        d.text((14, 7), "karl@proofofagent ~ e2e.sh  (live)", font=fntb, fill=ACCENT)
        d.text((W-180, 7), "Solana validator", font=fnt, fill=DIM)
        for y in range(ROWS):
            line = screen.buffer[y]
            for x in range(COLS):
                c = line[x]
                ch = c.data
                if ch in (" ", "\x00", ""):
                    continue
                d.text((x*CW, 30 + y*CH), ch, font=fntb if c.bold else fnt, fill=FG)
        idx = len(frames)
        img.save(f"{OUT}/frames/{idx:04d}.png")
        frames.append(idx)
    # completion: look for DONE in last screen lines
    tail = "".join(l for l in screen.display[-5:])
    if "== DONE ==" in tail:
        time.sleep(2.5)  # linger on the success screen
        # final frame
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 30], fill=(30, 41, 59))
        d.text((14, 7), "karl@proofofagent ~ e2e.sh  (live)", font=fntb, fill=ACCENT)
        for y in range(ROWS):
            line = screen.buffer[y]
            for x in range(COLS):
                c = line[x]
                ch = c.data
                if ch in (" ", "\x00", ""): continue
                d.text((x*CW, 30+y*CH), ch, font=fntb if c.bold else fnt, fill=FG)
        img.save(f"{OUT}/frames/{len(frames):04d}.png")
        frames.append(len(frames)-1)
        done = True

try:
    os.write(fd, b"\x04")
except Exception:
    pass
try:
    os.waitpid(pid, 0)
except Exception:
    pass
try:
    os.close(fd)
except Exception:
    pass

lines = [l.strip() for l in screen.display if l.strip()]
transcript = "\n".join(lines)
open(OUT + "/final_screen.txt", "w").write(transcript)
print("frames:", len(frames))
print("elapsed: %.1fs" % (time.time()-t0))
print("DONE detected:", done)
print("final tail:", "\n".join(lines[-6:]))
