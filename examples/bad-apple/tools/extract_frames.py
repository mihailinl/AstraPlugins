#!/usr/bin/env python3
"""
Extract frames from Bad Apple!! video and encode as compact binary format.

Usage:
    python extract_frames.py bad-apple.mp4 ../ui/frames.bin

Output format (frames.bin):
    Header:  4 bytes frameCount (LE u32)
             2 bytes width (LE u16)
             2 bytes height (LE u16)
    Per frame: 4 bytes dataLen (LE u32)
               dataLen bytes RLE data
    RLE:     [count, value] pairs where count is 1-255, value is 0 or 255

Dependencies: pip install opencv-python numpy
"""

import sys
import struct
import numpy as np

try:
    import cv2
except ImportError:
    print("Error: opencv-python is required. Install with: pip install opencv-python numpy")
    sys.exit(1)


def rle_encode(pixels: np.ndarray) -> bytes:
    """Run-length encode a 1D array of 0/255 values."""
    flat = pixels.flatten()
    result = bytearray()
    i = 0
    while i < len(flat):
        val = flat[i]
        count = 1
        while i + count < len(flat) and flat[i + count] == val and count < 255:
            count += 1
        result.append(count)
        result.append(val)
        i += count
    return bytes(result)


def extract(video_path: str, output_path: str, width: int = 120, height: int = 90):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Cannot open video '{video_path}'")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {total} frames at {fps:.1f} fps, output: {width}x{height}")

    frames_data = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convert to grayscale, resize, threshold to pure B&W
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
        _, binary = cv2.threshold(resized, 127, 255, cv2.THRESH_BINARY)

        rle = rle_encode(binary)
        frames_data.append(rle)

        frame_idx += 1
        if frame_idx % 500 == 0:
            print(f"  Processed {frame_idx}/{total} frames...")

    cap.release()

    # Write binary file
    frame_count = len(frames_data)
    total_size = 8  # header
    for f in frames_data:
        total_size += 4 + len(f)

    print(f"Writing {frame_count} frames, {total_size / 1024:.1f} KB...")

    with open(output_path, "wb") as f:
        # Header
        f.write(struct.pack("<I", frame_count))
        f.write(struct.pack("<H", width))
        f.write(struct.pack("<H", height))

        # Frames
        for rle in frames_data:
            f.write(struct.pack("<I", len(rle)))
            f.write(rle)

    print(f"Done! Wrote {output_path} ({total_size / 1024:.1f} KB, {frame_count} frames)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_frames.py <video.mp4> <output.bin> [width] [height]")
        print("Example: python extract_frames.py bad-apple.mp4 ../ui/frames.bin 120 90")
        sys.exit(1)

    video = sys.argv[1]
    output = sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 90

    extract(video, output, w, h)
