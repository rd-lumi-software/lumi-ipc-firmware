#!/usr/bin/env python3
"""Bounded H.264 RTP delivery check; does not decode video or save media."""
import argparse
import json
import re
import socket
import time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("host")
p.add_argument("output", type=Path)
p.add_argument("--seconds", type=int, default=15, choices=range(5, 61))
args = p.parse_args()
s = socket.create_connection((args.host, 18554), timeout=5)
base = f"rtsp://{args.host}:18554/main"
buf = b""
seq = 0
session = None


def receive():
    chunk = s.recv(65536)
    if not chunk:
        raise RuntimeError("RTSP connection closed")
    return chunk


def request(method, url, headers=""):
    global seq, buf
    seq += 1
    message = f"{method} {url} RTSP/1.0\r\nCSeq: {seq}\r\n"
    if session:
        message += f"Session: {session}\r\n"
    s.sendall((message + headers + "\r\n").encode())
    while b"\r\n\r\n" not in buf:
        buf += receive()
    header, buf = buf.split(b"\r\n\r\n", 1)
    length = re.search(rb"Content-Length:\s*(\d+)", header, re.I)
    size = int(length.group(1)) if length else 0
    while len(buf) < size:
        buf += receive()
    body, buf = buf[:size], buf[size:]
    if b"200 OK" not in header:
        raise RuntimeError(header.decode(errors="replace"))
    return header, body


try:
    _, sdp = request("DESCRIBE", base, "Accept: application/sdp\r\n")
    video = sdp.decode().split("m=video ", 1)[1].split("\nm=", 1)[0]
    control = re.search(r"a=control:([^\r\n]+)", video).group(1)
    track = control if control.startswith("rtsp://") else base + "/" + control
    h, _ = request("SETUP", track, "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n")
    session = re.search(rb"Session:\s*([^;\r\n]+)", h, re.I).group(1).decode()
    request("PLAY", base)
    print("RTSP_MONITOR_READY", flush=True)
    start = time.monotonic()
    packets = markers = gaps = 0
    timestamps = set()
    last_seq = last_time = None
    max_gap = 0
    s.settimeout(3)
    while time.monotonic() - start < args.seconds:
        while len(buf) < 4:
            buf += receive()
        if buf[0] != 36:
            raise RuntimeError("Unexpected interleaved RTSP record")
        channel, size = buf[1], int.from_bytes(buf[2:4], "big")
        while len(buf) < 4 + size:
            buf += receive()
        packet, buf = buf[4:4 + size], buf[4 + size:]
        if channel or len(packet) < 12:
            continue
        packets += 1
        number = int.from_bytes(packet[2:4], "big")
        if last_seq is not None and number != ((last_seq + 1) & 65535):
            gaps += 1
        last_seq = number
        markers += bool(packet[1] & 128)
        timestamp = int.from_bytes(packet[4:8], "big")
        if timestamp not in timestamps:
            now = time.monotonic()
            if last_time is not None:
                max_gap = max(max_gap, now - last_time)
            last_time = now
        timestamps.add(timestamp)
    result = dict(duration_seconds=round(time.monotonic() - start, 3),
                  video_rtp_packets=packets, marker_packets=markers,
                  unique_timestamps=len(timestamps), rtp_sequence_gaps=gaps,
                  max_timestamp_arrival_gap_ms=round(max_gap * 1000, 3),
                  validation="RTP delivery only; no decoding or frame retention",
                  passed=markers > args.seconds * 10 and gaps == 0)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
finally:
    s.close()
