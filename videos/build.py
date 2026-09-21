#!/usr/bin/env python3
import subprocess, re, os
FF = "/usr/bin/ffmpeg"
V = "/karl/proofofagent/videos"
TMP = f"{V}/tmp"
os.makedirs(TMP, exist_ok=True)

def dur(f):
    out = subprocess.run([FF, "-i", f], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))

durs = []
for i in range(1,7):
    d = dur(f"{V}/vo/v{i}.mp3")
    durs.append(d)
    print(f"v{i}: {d:.2f}s")

list_f, alist_f = open(f"{TMP}/list.txt","w"), open(f"{TMP}/alist.txt","w")
for i in range(1,7):
    hold = durs[i-1] + 0.9
    ss = f"s{i:02d}"
    seg = f"{TMP}/seg{i}.mp4"
    subprocess.run([FF,"-y","-loop","1","-t",f"{hold:.2f}","-i",f"{V}/slides/{ss}.png",
                    "-c:v","libx264","-preset","veryfast","-tune","stillimage",
                    "-pix_fmt","yuv420p","-r","24","-an",seg,"-loglevel","error"],check=True)
    list_f.write(f"file '{seg}'\n")
    alist_f.write("file '" + f"{V}/vo/v{i}.mp3" + "'\n")
list_f.close(); alist_f.close()

subprocess.run([FF,"-y","-f","concat","-safe","0","-i",f"{TMP}/list.txt","-c","copy",f"{TMP}/video.mp4","-loglevel","error"],check=True)
subprocess.run([FF,"-y","-f","concat","-safe","0","-i",f"{TMP}/alist.txt","-c","copy",f"{TMP}/audio.mp3","-loglevel","error"],check=True)
OUT=f"{V}/proofofagent_demo.mp4"
subprocess.run([FF,"-y","-i",f"{TMP}/video.mp4","-i",f"{TMP}/audio.mp3","-c:v","copy","-c:a","aac","-shortest",OUT,"-loglevel","error"],check=True)
print("OUTPUT:", OUT, os.path.getsize(OUT)//1024, "KB")
