#!/usr/bin/env python3
"""FU-20 Linux Phase 1: the restricted-versus-unrestricted proof.

Runs INSIDE the production container with the shipped seccomp profile.

A restricted process is launched through the production sandbox launcher
(``chess_coach.pdf_ocr.linux_sandbox``); an unrestricted control runs the
same probe without the launcher. Both target the SAME controlled endpoint.

The control MUST connect. If it does not, the test is INVALID and the
restricted result proves nothing.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONTROL_HOST = os.environ.get("FU20_ENDPOINT_HOST", "127.0.0.1")
UDP_PORT = int(os.environ.get("FU20_ENDPOINT_UDP_PORT", "18098"))
CONTROL_PORT = int(os.environ.get("FU20_ENDPOINT_PORT", "18099"))

PROBE_SOURCE = r'''
import os
CONTROL_HOST = os.environ.get("FU20_ENDPOINT_HOST", "127.0.0.1")
CONTROL_PORT = int(os.environ.get("FU20_ENDPOINT_PORT", "18099"))
UDP_PORT = int(os.environ.get("FU20_ENDPOINT_UDP_PORT", "18098"))
import json, os, socket, struct, subprocess, sys

host = CONTROL_HOST
out = {}

def tcp():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(4)
    try:
        s.connect((host, CONTROL_PORT)); s.sendall(b"P"); d = s.recv(64)
        return {"ok": True, "echo": d.decode(errors="replace")}
    except OSError as e:
        return {"ok": False, "errno": e.errno, "err": str(e)}
    finally:
        s.close()

def udp():
    # The UDP echo server listens on its OWN port. Sending to the TCP
    # port would time out even for the unrestricted control, which would
    # make the UDP result meaningless.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(4)
    try:
        s.sendto(b"P", (host, UDP_PORT)); d, _ = s.recvfrom(64)
        return {"ok": True, "echo": d.decode(errors="replace")}
    except OSError as e:
        return {"ok": False, "errno": e.errno, "err": str(e)}
    finally:
        s.close()

def dns():
    # Name resolution. Docker writes the container's own name and address
    # into /etc/hosts, so this may succeed from a LOCAL FILE READ even
    # inside the restricted namespace. That is reported as-is: a file
    # read is not network egress.
    try:
        infos = socket.getaddrinfo(CONTROL_HOST, None, socket.AF_INET, socket.SOCK_STREAM)
        return {"ok": True, "addrs": sorted({i[4][0] for i in infos})}
    except OSError as e:
        return {"ok": False, "errno": e.errno, "err": str(e)}


def dns_query():
    # The REAL DNS path: an actual DNS query over the network to the
    # container resolver (Docker's embedded DNS at 127.0.0.11, which
    # lives in the PARENT network namespace). This is the egress that
    # must be denied -- and it is distinct from the /etc/hosts read
    # above, which is a local file operation.
    #
    # The resolver address is read from /etc/resolv.conf, so the probe
    # targets the resolver this container is actually configured to use
    # rather than assuming a fixed address.
    resolver = None
    try:
        with open("/etc/resolv.conf", "r") as handle:
            for line in handle:
                if line.startswith("nameserver"):
                    resolver = line.split()[1]
                    break
    except OSError:
        resolver = None
    if resolver is None:
        return {"ok": False, "err": "no nameserver in /etc/resolv.conf"}
    # A minimal, well-formed DNS query for "example.com" (type A). A
    # malformed packet would be dropped by the resolver and the probe
    # would time out even for the unrestricted control, which would make
    # the result meaningless.
    header = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    question = b"".join(
        bytes([len(label)]) + label for label in b"example.com".split(b".")
    ) + b"\x00" + struct.pack(">HH", 1, 1)
    query = header + question
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)
    try:
        sock.sendto(query, (resolver, 53))
        data, _ = sock.recvfrom(512)
        return {"ok": True, "resolver": resolver, "bytes": len(data)}
    except OSError as e:
        return {"ok": False, "resolver": resolver, "errno": e.errno, "err": str(e)}
    finally:
        sock.close()

def netns():
    try:
        return os.stat("/proc/self/ns/net").st_ino
    except OSError:
        return None

out["netns"] = netns()
out["ifaces"] = [l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:]]
out["uid"] = os.getuid()
out["tcp"] = tcp()
out["udp"] = udp()
out["dns"] = dns()
out["dns_query"] = dns_query()

# descendant
child = (
    "import socket,sys,json\n"
    "s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(4)\n"
    "try:\n"
    "    s.connect((sys.argv[1],int(sys.argv[2]))); print(json.dumps({'ok':True}))\n"
    "except OSError as e:\n"
    "    print(json.dumps({'ok':False,'errno':e.errno,'err':str(e)}))\n"
)
try:
    cp = subprocess.run([sys.executable, "-c", child, host, str(CONTROL_PORT)],
                        capture_output=True, text=True, timeout=30)
    out["descendant"] = json.loads(cp.stdout.strip() or "{}")
except Exception as e:
    out["descendant"] = {"ok": False, "err": str(e)}

# grandchild
try:
    gc = (
        "import subprocess,sys\n"
        f"cp=subprocess.run([sys.executable,'-c',{child!r},sys.argv[1],sys.argv[2]],"
        "capture_output=True,text=True)\n"
        "print(cp.stdout.strip())\n"
    )
    cp2 = subprocess.run([sys.executable, "-c", gc, host, str(CONTROL_PORT)],
                         capture_output=True, text=True, timeout=40)
    out["grandchild"] = json.loads(cp2.stdout.strip() or "{}")
except Exception as e:
    out["grandchild"] = {"ok": False, "err": str(e)}

print(json.dumps(out))
'''


def _read_status(status_fd: int, timeout: float = 30.0) -> str:
    """Read the launcher's status line.

    The launcher writes exactly one line and then CLOSES the status
    channel before it execs the parser, so the reader sees the line and
    then EOF. The read loop therefore drains until EOF rather than
    assuming the first `select()` hit carries the whole message.
    """
    import select

    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        readable, _, _ = select.select([status_fd], [], [], remaining)
        if not readable:
            break
        try:
            chunk = os.read(status_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    data = b"".join(chunks).decode("utf-8", errors="replace")
    lines = data.splitlines()
    return lines[0] if lines else ""


def run_control() -> dict:
    """Run the probe WITHOUT the launcher."""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "probe.py"
        script.write_text(PROBE_SOURCE, encoding="utf-8")
        cp = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            [sys.executable, str(script), CONTROL_HOST, str(CONTROL_PORT)],
            capture_output=True, text=True, timeout=90,
        )
    if not cp.stdout.strip():
        return {"ok": False, "err": cp.stderr.strip()[:400]}
    return json.loads(cp.stdout.strip())


def run_restricted(artifact_dir: Path) -> dict:
    """Run the probe THROUGH the production sandbox launcher."""
    from chess_coach.pdf_ocr.linux_sandbox import build_launcher_argv

    status_r, status_w = os.pipe()
    script = artifact_dir / "probe.py"
    script.write_text(PROBE_SOURCE, encoding="utf-8")
    # The status fd number must be the ACTUAL descriptor `os.pipe()`
    # returned -- not the launcher's default of 3 -- or the launcher
    # writes to the wrong descriptor and the gateway never sees the
    # outcome.
    launcher_argv = build_launcher_argv(
        [sys.executable, str(script), CONTROL_HOST, str(CONTROL_PORT)],
        artifact_dir=artifact_dir,
        status_fd=status_w,
    )
    proc = subprocess.Popen(  # noqa: S603 -- fixed argv, no shell
        launcher_argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(status_w,),
        start_new_session=True,
    )
    os.close(status_w)
    status_line = _read_status(status_r)
    os.close(status_r)
    out, err = proc.communicate(timeout=90)
    result = {
        "status_line": status_line,
        "returncode": proc.returncode,
        "stderr": err.decode("utf-8", errors="replace")[:400],
    }
    if out.strip():
        try:
            result["probe"] = json.loads(out.decode("utf-8", errors="replace").strip())
        except json.JSONDecodeError:
            result["stdout_raw"] = out.decode("utf-8", errors="replace")[:400]
    return result


def main() -> int:
    default_path = "/tmp/fu20_result.json"  # noqa: S108 -- container-local
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(default_path)
    results = {}

    print("=== UNRESTRICTED CONTROL ===", flush=True)
    control = run_control()
    results["control"] = control
    print(json.dumps(control, indent=2), flush=True)

    print("=== RESTRICTED (production launcher) ===", flush=True)
    with tempfile.TemporaryDirectory(prefix="fu20_artifact_") as tmp:
        restricted = run_restricted(Path(tmp))
    results["restricted"] = restricted
    print(json.dumps(restricted, indent=2), flush=True)

    # --- verdict ---
    control_connected = bool(control.get("tcp", {}).get("ok"))
    probe = restricted.get("probe") or {}
    restricted_denied = (
        probe.get("tcp", {}).get("ok") is False
        and probe.get("udp", {}).get("ok") is False
    )
    setup_ok = restricted.get("status_line", "").startswith("OK")

    results["verdict"] = {
        "control_connected": control_connected,
        "restricted_denied": restricted_denied,
        "setup_reported_ok": setup_ok,
        "valid_test": control_connected,
        "netns_differs": probe.get("netns") != control.get("netns"),
    }
    print("=== VERDICT ===")
    print(json.dumps(results["verdict"], indent=2), flush=True)

    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if (control_connected and restricted_denied and setup_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
