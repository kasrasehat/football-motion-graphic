import { Config } from "@remotion/cli/config";

// Deterministic, frame-exact output. Audio is muxed later by the Python engine (ffmpeg).
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");
