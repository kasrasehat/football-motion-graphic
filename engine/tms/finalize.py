"""Final assembly helpers: mux (video stream copied, never re-encoded) and media probes."""
from __future__ import annotations

import json
from pathlib import Path

from tms.audio import wav


def mux(video: Path, audio_wav: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    wav.run([wav.ffmpeg(), "-v", "error", "-y", "-i", video, "-i", audio_wav, "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", wav.SR, "-ac", 2, "-movflags", "+faststart", out])


def probe(path: Path) -> dict:
    p = wav.run([wav.ffprobe(), "-v", "error", "-count_frames", "-show_entries",
                 "stream=codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate,nb_read_frames,sample_rate,channels,duration"
                 ":format=duration,size,bit_rate", "-of", "json", path])
    d = json.loads(p.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), {})
    return {"video": v, "audio": a, "format": d.get("format", {})}
