#!/usr/bin/env python3
"""Local media converter (needs ffmpeg). The site already exports WAV/MP3 in the browser; this covers the rest.
  mediakit.py mp4   song.mp3|wav [out.mp4]     audio -> video with an animated waveform (for sharing)
  mediakit.py mp3   in.wav|mp4   [out.mp3]     any audio/video -> MP3
  mediakit.py wav   in.mp3|mp4   [out.wav]     any audio/video -> WAV (44.1 kHz stereo)
  mediakit.py audio in.mp4       [out.mp3]     pull the soundtrack out of a video you already have"""
import subprocess, sys
from pathlib import Path

def run(args):
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", *args])
    if p.returncode:
        sys.exit(p.returncode)

def main(argv):
    if len(argv) < 3 or argv[1] not in ("mp4", "mp3", "wav", "audio"):
        sys.exit(__doc__)
    kind, src = argv[1], Path(argv[2])
    if not src.exists():
        sys.exit(f"not found: {src}")
    ext = {"mp4": ".mp4", "mp3": ".mp3", "wav": ".wav", "audio": ".mp3"}[kind]
    out = Path(argv[3]) if len(argv) > 3 else src.with_suffix(ext) if src.suffix != ext else src.with_name(src.stem + "_out" + ext)
    if kind == "mp4":
        run(["-i", str(src), "-filter_complex", "[0:a]showwaves=s=1280x720:mode=cline:colors=0xf4b942:rate=30,format=yuv420p[v]",
             "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)])
    elif kind == "wav":
        run(["-i", str(src), "-vn", "-ar", "44100", "-ac", "2", str(out)])
    else:
        run(["-i", str(src), "-vn", "-codec:a", "libmp3lame", "-b:a", "192k", str(out)])
    print(out)

main(sys.argv)
