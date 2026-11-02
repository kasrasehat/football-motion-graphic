---
name: ffmpeg-av
description: Audio/video engineering conventions of this project - the 30 fps / 48 kHz clock, sample-exact voice placement, envelope ducking, two-pass loudnorm targets, muxing without re-encoding, probes, and the A/V sync calibration test. Use when debugging audio levels, sync, or final file properties.
---

# A/V conventions

- **Clock**: 30 fps exactly, 48 kHz audio → **1600 samples per frame**. Every time in `build/timeline.json` is an
  integer frame; voice clips are placed at sample `frame × 1600` (numpy, not `adelay`).
- **Ducking**: music gain follows the timeline's `duck.windows` (−10 dB, 150 ms attack, 450 ms release) — computed,
  not sidechain-compressed, so it is exact and testable (margin ≥ 9 dB, FQ-04).
- **Loudness**: two-pass `loudnorm` to −14 LUFS, true peak −1.5 dBTP (verify ≤ −1.0 after AAC), LRA ≤ 11; when ffmpeg
  would fall back to dynamic mode we apply gain + limiter instead (`normalization` in the report says which).
- **Video**: Remotion renders h264 High, `yuv420p`, BT.709, 30/1. **Muxing copies the video stream** (`-c:v copy`) and
  encodes AAC 192 kb/s 48 kHz stereo with `+faststart`. Never re-encode the video to fix audio.
- **Paths**: the repo path has spaces — subprocesses use argv lists; no file paths inside filtergraphs (flite reads
  `textfile=line.txt` from its cwd).
- **Calibration**: `.venv/Scripts/tms qa sync-test` renders white flash frames, places 20 ms clicks at the same
  frames, muxes, then detects both from the final file. Pass = every offset ≤ 1 frame (it measures 0 today).
- Probe a file: `ffprobe -v error -count_frames -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames -of json <file>`.
