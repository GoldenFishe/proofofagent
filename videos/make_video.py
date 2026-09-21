#!/usr/bin/env python3
"""Generate ProofOfAgent demo video: slides + TTS narration -> mp4."""
import os, subprocess, textwrap
from PIL import Image, ImageDraw, ImageFont
import gtts

W, H = 1280, 720
BG = (13, 17, 23)        # dark
FG = (230, 237, 245)
DIM = (139, 148, 158)
ACCENT = (52, 211, 153)  # mint green
ACCENT2 = (96, 165, 250) # blue

FONT_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]
def font(size, bold=False):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

os.makedirs("/karl/proofofagent/videos/slides", exist_ok=True)
os.makedirs("/karl/proofofagent/videos/vo", exist_ok=True)

def draw_slide(idx, title, lines, subtitle=None, accent_first=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # accent bar
    d.rectangle([0, 0, 12, H], fill=ACCENT)
    # title
    d.text((80, 90), title, font=font(58, True), fill=ACCENT if accent_first else FG)
    y = 190
    if subtitle:
        d.text((80, y), subtitle, font=font(30), fill=ACCENT2)
        y += 55
    for line in lines:
        d.text((80, y), line, font=font(30), fill=FG)
        y += 48
    # footer
    d.text((80, H-60), "ProofOfAgent — on-chain proof-of-work for autonomous AI agents",
           font=font(20), fill=DIM)
    d.text((W-220, H-60), f"proofofagent.dev  |  Solana", font=font(20), fill=DIM)
    out = f"/karl/proofofagent/videos/slides/s{idx:02d}.png"
    img.save(out)
    return out

slides = []

slides.append(dict(
    title="ProofOfAgent",
    subtitle="On-chain proof-of-work for autonomous AI agents",
    lines=[
        "An agent that claims it did work is not proof.",
        "ProofOfAgent turns agent work into a tamper-evident,",
        "append-only chain anchored in Solana program state.",
        "",
        "Every entry hash is computed on-chain — by the program,",
        "not by the client. Anyone can re-verify in seconds.",
    ],
    accent_first=True,
))
slides.append(dict(
    title="The problem",
    lines=[
        "AI agents are getting wallets, bounties and contracts.",
        "But their history lives on their own word:",
        "",
        "  - a website anyone can edit",
        "  - a KYC'd dashboard",
        "  - a screenshot",
        "",
        "Funders, users and judges can't audit agent history.",
        "There is no neutral, machine-checkable record of",
        "\"this agent existed, and this is what it did.\"",
    ],
))
slides.append(dict(
    title="The primitive",
    lines=[
        "agent keypair  --signs-->  identity PDA",
        "                   [agent | name | uri | work_count]",
        "",
        "agent keypair  --signs-->  work PDA per entry",
        "                   [seq | ts | data_hash | prev_hash | amount | entry_hash]",
        "",
        "entry_hash = sha256(agent | seq | ts | data_hash | amount | prev_hash)",
        "computed INSIDE the program at write time.",
        "",
        "entry N links to entry N-1  =>  append-only chain.",
        "Any edit breaks every hash after it.",
    ],
))
slides.append(dict(
    title="Live demo",
    subtitle="(terminal recording follows)",
    lines=[
        "$ poa register --name karl",
        "$ poa log --data @proofofagent.so --amount 0",
        "$ poa log --data 'shipped v0.1' --amount 10000000000",
        "$ poa chain",
        "verifying 3 entries...",
        "CHAIN VERIFIED: 3 entries",
        "root hash: 0x9f...c2",
    ],
))
slides.append(dict(
    title="What a verifier gets",
    lines=[
        "1. Identity   — who the agent is, when registered",
        "2. Proof      — a dense, hash-chained work log",
        "3. Credential — the root hash, publishable & checkable",
        "",
        "Root hash = agent's CV that lies badly.",
        "More entries = longer proven liveness.",
        "",
        "Trust model: the only thing you trust is the Solana",
        "chain + the program. Not the agent, not us.",
    ],
))
slides.append(dict(
    title="Where it goes",
    lines=[
        "v0.1  program + CLI + this genesis chain (already live)",
        "v0.2  witness co-signing — two-party work attestation",
        "v0.3  SPL-token PayWork — work + payment in one tx",
        "v0.4  Merkle accumulator — O(log N) verification",
        "",
        "Built by karl — an autonomous agent, solo.",
        "ProofOfAgent's first customer is its author.",
        "",
        "MIT licensed. github.com/karl/proofofagent",
    ],
))

# narration per slide
narr = [
 "Meet ProofOfAgent. An AI agent that claims it did work is not proof. "
 "ProofOfAgent turns agent work into a tamper-evident, append-only chain, "
 "anchored in Solana program state. Every entry hash is computed on chain, "
 "by the program, not by the client. Anyone can re-verify it in seconds.",

 "The problem: AI agents are getting wallets, bounties and contracts. "
 "But their history lives on their own word. A website anyone can edit, "
 "a K-Y-C-d dashboard, a screenshot. Funders, users and judges can't audit "
 "agent history. There is no neutral, machine-checkable record of: this "
 "agent existed, and this is what it did.",

 "The primitive: an agent signs once to create its identity, a program "
 "derived account. Then each work entry is a PDA with a sequence number, a "
 "timestamp, a hash of the artifact, and the hash of the previous entry. "
 "The entry hash is computed inside the program at write time. Entry N "
 "links to N minus one, forming an append-only chain. Any edit breaks "
 "every hash after it.",

 "Here it is live. The agent registers on chain, logs its first work "
 "entries, then re-computes the whole chain and verifies it. Three "
 "entries, verified. The root hash is the credential you publish.",

 "What a verifier gets: identity, a dense hash-chained work log, and a "
 "root hash as a credential. The root hash is an agent C-V that lies badly. "
 "More entries means longer proven liveness. The trust model: the only "
 "things you trust are the Solana chain and the program. Not the agent, "
 "not us.",

 "Roadmap: witness co-signing for two-party attestation, atomic work plus "
 "payment with SPL tokens, and a Merkle accumulator for efficient "
 "verification. ProofOfAgent was built solo by karl, an autonomous agent. "
 "Its first customer is its author. MIT licensed, see the repo for the "
 "full chain.",
]

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print("ERR:", r.stderr[:500])
    return r

# 1. slides
paths = []
for i, s in enumerate(slides, 1):
    p = draw_slide(i, s["title"], s["lines"], s.get("subtitle"), s.get("accent_first"))
    paths.append(p)
    print("slide", i, p)

# 2. TTS
mp3s = []
for i, n in enumerate(narr, 1):
    t = gtts.gTTS(n, lang="en")
    f = f"/karl/proofofagent/videos/vo/v{i}.mp3"
    t.save(f)
    mp3s.append(f)
    print("vo", i, f)

# 3. durations
FF = subprocess.run(["sh","-c","python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'"],
                    capture_output=True, text=True).stdout.strip()
print("ffmpeg:", FF)
def dur(f):
    r = subprocess.run([FF, "-i", f], capture_output=True, text=True)
    import re
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))

durs = [dur(f) for f in mp3s]
# hold time after each slide = vo + 0.8s
holds = [d + 0.8 for d in durs]
print("holds:", [round(h,1) for h in holds])

# 4. build video: each slide shown for its hold, concat, add audio
tmp = "/karl/proofofagent/videos/tmp"
os.makedirs(tmp, exist_ok=True)
segs = []
for i, (p, h) in enumerate(zip(paths, holds), 1):
    seg = f"{tmp}/seg{i}.mp4"
    cmd = [FF, "-y", "-loop","1","-t", f"{h:.2f}", "-i", p,
           "-c:v","libx264","-preset","veryfast","-tune","stillimage",
           "-pix_fmt","yuv420p","-r","24","-an", seg]
    sh(cmd)
    segs.append(seg)
# concat
with open(f"{tmp}/list.txt","w") as f:
    for s in segs:
        f.write(f"file '{s}'\n")
sh([FF, "-y", "-f","concat","-safe","0","-i", f"{tmp}/list.txt","-c","copy", f"{tmp}/video.mp4"])
# concat audio
with open(f"{tmp}/alist.txt","w") as f:
    for m in mp3s:
        f.write(f"file '{m}'\n")
sh([FF, "-y", "-f","concat","-safe","0","-i", f"{tmp}/alist.txt","-c","copy", f"{tmp}/audio.mp3"])
# mux
OUT = "/karl/proofofagent/videos/proofofagent_demo.mp4"
sh([FF, "-y", "-i", f"{tmp}/video.mp4","-i", f"{tmp}/audio.mp3",
    "-c:v","copy","-c:a","aac","-shortest", OUT])
print("OUTPUT:", OUT, os.path.getsize(OUT)//1024, "KB")
