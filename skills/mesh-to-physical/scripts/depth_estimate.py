#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "transformers",
#   "torch",
#   "pillow",
#   "numpy",
# ]
# ///
"""
Monocular depth estimation for turning a reference image into a displacement
map. Uses Depth Anything V2 (small). Output is an 8-bit grayscale PNG where
BRIGHTER = CLOSER (nearer the camera) — feed it straight into a Blender
Displace modifier (white pushes out).

Usage:
    ./depth_estimate.py INPUT.jpg OUTPUT_depth.png [--invert] [--upscale N]
"""
import argparse
import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--invert", action="store_true",
                    help="flip near/far (use if the relief comes out inverted)")
    ap.add_argument("--upscale", type=int, default=1,
                    help="upscale the input NxN before estimation (small masks)")
    ap.add_argument("--model", default="depth-anything/Depth-Anything-V2-Small-hf")
    args = ap.parse_args()

    from transformers import pipeline

    img = Image.open(args.inp).convert("RGB")
    if args.upscale > 1:
        img = img.resize((img.width * args.upscale, img.height * args.upscale),
                         Image.LANCZOS)
    print(f"input {args.inp}  size={img.size}  model={args.model}")

    pipe = pipeline("depth-estimation", model=args.model)
    depth = pipe(img)["predicted_depth"]          # torch tensor, larger = closer
    d = depth.squeeze().cpu().numpy().astype("float32")
    # normalise to 0..255
    d = (d - d.min()) / (d.max() - d.min() + 1e-9)
    if args.invert:
        d = 1.0 - d
    arr = (d * 255).astype("uint8")
    out = Image.fromarray(arr).resize(img.size, Image.LANCZOS)
    out.save(args.out)
    print(f"saved depth {args.out}  size={out.size}  (brighter = closer)")


if __name__ == "__main__":
    main()
