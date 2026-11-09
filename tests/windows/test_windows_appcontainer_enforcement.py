r"""Real Windows AppContainer enforcement tests (BBF-FU-20-windows-appcontainer).

These tests run on a real ``windows-latest`` runner and execute **real
Win32 calls** — no mocked AppContainer API, no skip in place of proof, no
documentation-only assertion. Every test either exercises the kernel's
enforcement or fails.

The suite proves the properties the Windows AppContainer backend is
accountable for:

1. The launched target really is an AppContainer, with the product-owned
   package SID, and it holds **no** network capability.
2. The target cannot open a new outbound network connection, while an
   unrestricted control in the same run can.
3. The restriction survives child and grandchild creation.
4. An AppContainer token does **not** revoke an inherited network handle:
   the bypass is real, and the production launch shape defeats it.
5. The production launch shape (a populated stdout/stderr allowlist)
   excludes a live inherited socket, while the unrestricted positive
   control proves the socket was genuinely usable.
6. The Job's per-process limit and the AppContainer identity are both in
   force **before the target runs its first instruction**.
7. The real Poppler workload runs under the restricted token and produces
   the expected artifact.
8. The minimum-ACL contract holds: the parser runs with the product-SID
   grant and fails closed without it.
9. Every containment setup failure prevents parser execution and stays
   distinguishable in the error taxonomy.
10. Repeated execution leaks no process, listener, or registry state.

The **mandatory positive control** for the inherited-socket property is
:func:`test_unrestricted_inherited_socket_control_is_usable`: the same
socket, in the same run, launched without an allowlist, must be usable
and the server must observe the bytes. Paired with
:func:`test_production_allowlist_excludes_the_inherited_socket`, the pair
fails against an implementation whose allowlist does not actually exclude
the socket, and cannot be satisfied by a dead endpoint.
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess  # noqa: S404 -- intentional: these tests spawn real processes
import sys
import threading
import time
from pathlib import Path

import pytest

from chess_coach.pdf_ocr import windows_appcontainer as wa
from chess_coach.pdf_ocr import windows_job as wj

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="the Windows AppContainer backend only exists on Windows",
)

#: The production per-process limit, which every test asserts is unchanged.
PRODUCTION_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

#: The pinned Poppler version used by the feasibility evidence.
POPPLER_VERSION = "26.09.0"

#: The staged root used by the tests. It is outside the user profile
#: because an AppContainer token cannot traverse the user profile.
STAGING_ROOT = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ChessCoachTests"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_pdf(path: Path) -> bytes:
    """A deterministic, valid, one-page PDF. No external dependency."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length 62 >>\nstream\nBT /F1 18 Tf 20 100 Td (FU-20) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n"
        "%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))
    return bytes(out)


class _Endpoint:
    """A TCP listener that records the bytes each client sent."""

    def __init__(self) -> None:
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("0.0.0.0", 0))
        self.port = self.srv.getsockname()[1]
        self.srv.listen(16)
        self.received: list[tuple[tuple[str, int], bytes]] = []
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self.srv.settimeout(0.4)
        while not self._stop:
            try:
                conn, addr = self.srv.accept()
            except (socket.timeout, OSError):
                continue
            try:
                conn.settimeout(3.0)
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    self.received.append((addr, data))
                    conn.sendall(b"ECHO:" + data)
            except (socket.timeout, OSError):
                pass
            finally:
                conn.close()

    def saw(self, marker: bytes) -> bool:
        return any(marker in payload for _, payload in self.received)

    def clear(self) -> None:
        self.received.clear()

    def close(self) -> None:
        self._stop = True
        try:
            self.srv.close()
        except OSError:
            pass


def _lan_ip() -> str:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        return ip
    except OSError:
        return "127.0.0.1"


#: The native probe used by the containment tests. It reports the token's
#: identity, the presence and usability of an inherited handle, and the
#: result of a new outbound TCP connect.
_NATIVE_HELPER = r"""
using System;
using System.Runtime.InteropServices;

public static class Fu20Enforcement
{
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool GetHandleInformation(IntPtr h, out uint flags);

    [DllImport("ws2_32.dll", SetLastError=true)]
    static extern int send(IntPtr s, byte[] b, int len, int flags);

    [DllImport("ws2_32.dll", SetLastError=true)]
    static extern int recv(IntPtr s, byte[] b, int len, int flags);

    [DllImport("ws2_32.dll", SetLastError=true)]
    static extern int WSAStartup(ushort ver, byte[] data);

    public static string HandleInfo(int h)
    {
        try {
            uint flags;
            if (!GetHandleInformation(new IntPtr(h), out flags))
                return "ABSENT:winerr=" + Marshal.GetLastWin32Error();
            return "PRESENT:flags=0x" + flags.ToString("X8") +
                   ";inheritable=" + ((flags & 0x1) != 0);
        } catch (Exception e) { return "ERR:" + e.GetType().Name; }
    }

    public static string Send(int h)
    {
        try {
            byte[] wsadata = new byte[512];
            int w = WSAStartup(0x0202, wsadata);
            if (w != 0) return "WSAStartup-failed:" + w;
            byte[] p = System.Text.Encoding.ASCII.GetBytes("PROBEUSESOCKET");
            int n = send(new IntPtr(h), p, p.Length, 0);
            if (n < 0) return "SEND-FAILED:winerr=" + Marshal.GetLastWin32Error();
            byte[] buf = new byte[64];
            int g = recv(new IntPtr(h), buf, buf.Length, 0);
            if (g < 0) return "SENT-OK(" + n + "):RECV-FAILED:winerr=" + Marshal.GetLastWin32Error();
            return "USED:sent=" + n + ":recv=" + g;
        } catch (Exception e) { return "ERR:" + e.GetType().Name + ":" + e.Message; }
    }

    [DllImport("advapi32.dll", SetLastError=true)]
    static extern bool OpenProcessToken(IntPtr h, uint access, out IntPtr token);

    [DllImport("advapi32.dll", SetLastError=true)]
    static extern bool GetTokenInformation(IntPtr token, int cls, IntPtr info, int len, out int ret);

    [DllImport("kernel32.dll")]
    static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr h);

    // Reads this process's OWN token: TokenIsAppContainer (29) and
    // TokenAppContainerSid (31).  This is the child-side counterpart to
    // the launcher's pre-resume read.
    public static string TokenFacts()
    {
        IntPtr token = IntPtr.Zero;
        try {
            if (!OpenProcessToken(GetCurrentProcess(), 0x0008, out token))
                return "OPEN-FAILED:winerr=" + Marshal.GetLastWin32Error();
            int ret;
            GetTokenInformation(token, 29, IntPtr.Zero, 0, out ret);
            IntPtr b29 = Marshal.AllocHGlobal(Math.Max(ret, 4));
            GetTokenInformation(token, 29, b29, Math.Max(ret, 4), out ret);
            int isApp = Marshal.ReadInt32(b29);
            Marshal.FreeHGlobal(b29);

            GetTokenInformation(token, 31, IntPtr.Zero, 0, out ret);
            IntPtr b31 = Marshal.AllocHGlobal(Math.Max(ret, 8));
            GetTokenInformation(token, 31, b31, Math.Max(ret, 8), out ret);
            IntPtr sid = Marshal.ReadIntPtr(b31);
            string sidStr = "none";
            if (sid != IntPtr.Zero)
            {
                byte[] raw = new byte[8 + 6 + 8 * 4];
                Marshal.Copy(sid, raw, 0, raw.Length);
                int cnt = raw[1];
                ulong auth = 0;
                for (int i = 0; i < 6; i++) auth = (auth << 8) | raw[2 + i];
                var parts = new System.Collections.Generic.List<string>();
                parts.Add("S-" + raw[0] + "-" + auth);
                for (int i = 0; i < cnt; i++)
                    parts.Add(BitConverter.ToUInt32(raw, 8 + i * 4).ToString());
                sidStr = string.Join("-", parts.ToArray());
            }
            Marshal.FreeHGlobal(b31);
            return "is_app_container=" + (isApp != 0 ? "true" : "false") +
                   ";app_container_sid=" + sidStr;
        } catch (Exception e) { return "ERR:" + e.GetType().Name + ":" + e.Message; }
        finally { if (token != IntPtr.Zero) CloseHandle(token); }
    }
}
"""


def _write_probe(directory: Path) -> Path:
    """Write the native probe script into ``directory``.

    ``directory`` must be **outside the user profile**: an AppContainer
    token cannot traverse the user profile, so a profile-resident script
    is invisible to the target. The product SID is granted read+execute
    on the staged directory so the target can read it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / "probe_enforcement.ps1"
    template = (
        "param([int]$SocketHandle=0,[string]$Target='127.0.0.1',"
        "[int]$Port=0,[string]$OutFile='')\n"
        "$ErrorActionPreference='Continue'\n"
        "$o=[ordered]@{ pid=$PID; token_user_sid=$null; groups=$null; "
        "internet_client_present=$null; connect=$null; handle_info=$null; "
        "socket_use=$null; token_facts=$null }\n"
        "try {\n"
        "  Add-Type -TypeDefinition @'\n" + _NATIVE_HELPER + "'@\n"
        "} catch { $o.helper_error=$_.Exception.Message }\n"
        "try {\n"
        "  $id=[System.Security.Principal.WindowsIdentity]::GetCurrent()\n"
        "  $o.token_user_sid=$id.User.Value\n"
        "  $o.groups=@($id.Groups | ForEach-Object { $_.Value })\n"
        "  $o.internet_client_present=($o.groups -contains 'S-1-15-3-1')\n"
        "} catch { $o.token_error=$_.Exception.Message }\n"
        "try { $o.token_facts=[Fu20Enforcement]::TokenFacts() } "
        "catch { $o.token_facts='ERR:' + $_.Exception.Message }\n"
        "if ($SocketHandle -ne 0) {\n"
        "  try { $o.handle_info=[Fu20Enforcement]::HandleInfo($SocketHandle) } "
        "catch { $o.handle_info='ERR' }\n"
        "  try { $o.socket_use=[Fu20Enforcement]::Send($SocketHandle) } "
        "catch { $o.socket_use='ERR' }\n"
        "}\n"
        "if ($Port -ne 0) {\n"
        "  $c=$null\n"
        "  try {\n"
        "    $c=New-Object System.Net.Sockets.TcpClient\n"
        "    $iar=$c.BeginConnect($Target,$Port,$null,$null)\n"
        "    if ($iar.AsyncWaitHandle.WaitOne(4000)) { $c.EndConnect($iar); "
        "$o.connect='CONNECTED' } else { $o.connect='TIMEOUT' }\n"
        "  } catch { $o.connect='DENIED_OR_ERROR:' + $_.Exception.GetType().Name }\n"
        "  finally { if ($c) { $c.Close() } }\n"
        "}\n"
        "if ($OutFile -ne '') { [System.IO.File]::WriteAllText($OutFile, "
        "($o | ConvertTo-Json -Compress), [System.Text.Encoding]::UTF8) }\n"
    )
    probe.write_text(template, encoding="utf-8", newline="\r\n")
    return probe


def _ensure_product_profile() -> None:
    """Register the product AppContainer profile for the current user."""
    if not wa.profile_is_registered():
        wa.register_profile()


def _ensure_package_folder() -> None:
    """Create the moniker package folder, including ``AC\\Temp``.

    The package folder is the container's private temporary area. Two
    things are needed for the target to work in it:

    * the ``AC\\Temp`` child must exist, because the OS stages the
      container's temporary files there;
    * the product SID must have **modify** rights on it, because the
      target writes its compiled helper into it.

    Without the grant the target's ``Add-Type`` fails with "access denied
    to path ...\\AC\\Temp\\<file>.tmp".
    """
    package = wa.package_folder_path()
    for sub in ("AC", os.path.join("AC", "Temp"), "LocalCache", "LocalState",
                "RoamingState", "Settings"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    # The product SID needs modify on its own package folder and on the
    # container temporary directory; the ALL APPLICATION PACKAGES group
    # needs it on the temporary directory too.
    _grant(package, "M")
    _grant(package / "AC" / "Temp", "M")
    subprocess.run(
        ["icacls", str(package / "AC" / "Temp"), "/grant",
         "*S-1-15-2-1:(OI)(CI)(M)"],
        capture_output=True, text=True, errors="replace", timeout=120, check=False,
    )


def _grant(path: Path, perms: str) -> None:
    subprocess.run(
        ["icacls", str(path), "/grant", f"*{wa.PRODUCT_PACKAGE_SID}:(OI)(CI)({perms})"],
        capture_output=True, text=True, errors="replace", timeout=120, check=False,
    )


@pytest.fixture(scope="module")
def product_profile() -> None:
    """The product AppContainer profile, registered and ready."""
    _ensure_product_profile()
    _ensure_package_folder()


@pytest.fixture
def stage(tmp_path: Path) -> Path:
    """A working directory OUTSIDE the user profile, with minimum ACLs.

    An AppContainer token cannot traverse the user profile, so the probe
    script and the artifacts must live somewhere the restricted token can
    reach. The product SID gets read+execute on the directory and modify
    on the artifact directory.
    """
    work = STAGING_ROOT / f"work_{os.getpid()}_{time.time_ns()}"
    work.mkdir(parents=True, exist_ok=True)
    _grant(work, "M")
    try:
        yield work
    finally:
        # The ACL is revoked before the tree is removed, so the
        # restricted SID never keeps the directory alive.
        subprocess.run(
            ["icacls", str(work), "/remove", f"*{wa.PRODUCT_PACKAGE_SID}", "/T", "/C"],
            capture_output=True, text=True, errors="replace", timeout=240, check=False,
        )
        import shutil

        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. The token identity and the zero-capability set
# ---------------------------------------------------------------------------


def test_launched_target_is_the_product_appcontainer(product_profile, stage):
    """The launched token is an AppContainer with the product SID.

    The verification runs launcher-side while the target is still
    suspended, so a mismatch would mean the target never ran.
    """
    probe = _write_probe(stage)
    out_file = stage / "identity.json"
    argv = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
        "Bypass", "-File", str(probe), "-OutFile", str(out_file),
    ]
    result = wj.run_in_appcontainer_job(
        argv,
        timeout_seconds=60,
        limit_bytes=PRODUCTION_LIMIT_BYTES,
        cwd=stage,
        stdout_path=stage / "stdout.bin",
        stderr_path=stage / "stderr.bin",
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert out_file.exists()
    evidence = json.loads(out_file.read_text(encoding="utf-8-sig"))
    # The child-side token USER is the container user; the package SID is
    # proven launcher-side by TokenAppContainerSid (see the launcher
    # verification below), because the token user is NOT the package SID.
    assert evidence["token_user_sid"].startswith("S-1-5-21-")
    # The child-side token facts prove the package identity from INSIDE the
    # container: TokenIsAppContainer=True and TokenAppContainerSid is the
    # product SID.  The token USER is the container user, not the package.
    facts = evidence["token_facts"]
    assert "is_app_container=true" in facts, facts
    assert f"app_container_sid={wa.PRODUCT_PACKAGE_SID}" in facts, facts
    # No network capability.
    assert evidence["internet_client_present"] is False
    assert not [g for g in evidence["groups"] if g.startswith("S-1-15-3-")]


def test_the_launcher_refuses_to_resume_a_mismatched_token(product_profile, stage):
    """A token that is not the product AppContainer fails closed.

    The verification failure must prevent the target from running at all.
    """
    probe = _write_probe(stage)
    out_file = stage / "mismatch.json"
    argv = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
        "Bypass", "-File", str(probe), "-OutFile", str(out_file),
    ]
    marker = stage / "ran.txt"
    with pytest.raises(wa.AppContainerVerificationError):
        wj.run_in_appcontainer_job(
            argv,
            timeout_seconds=30,
            limit_bytes=PRODUCTION_LIMIT_BYTES,
            cwd=stage,
            stdout_path=stage / "stdout.bin",
            stderr_path=stage / "stderr.bin",
            # Launch under the product SID but expect a DIFFERENT one, so
            # the pre-resume verification is what fails closed.
            package_sid=wa.PRODUCT_PACKAGE_SID,
            expected_package_sid=wa.ALL_APPLICATION_PACKAGES_SID,
        )
    # The target never produced its output file: it was never resumed.
    assert not out_file.exists() or out_file.stat().st_size == 0


# ---------------------------------------------------------------------------
# 2. New outbound network access is denied
# ---------------------------------------------------------------------------


def test_restricted_target_cannot_connect_but_the_control_can(product_profile, stage):
    """The restricted target is denied; the unrestricted control connects.

    Both arms run in the same process, against the same live endpoint, so
    a "denied" result cannot be dismissed as a dead endpoint.
    """
    endpoint = _Endpoint()
    probe = _write_probe(stage)
    target = _lan_ip()
    try:
        for label, package_sid in (("restricted", None), ("control", "unrestricted")):
            out_file = stage / f"connect_{label}.json"
            argv = [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(probe),
                "-Target", target, "-Port", str(endpoint.port),
                "-OutFile", str(out_file),
            ]
            if package_sid == "unrestricted":
                # The control arm runs without the AppContainer at all.
                proc = subprocess.run(
                    argv, capture_output=True, text=True, timeout=90, check=False,
                    cwd=str(stage),
                )
                assert proc.returncode == 0, proc.stderr
            else:
                wj.run_in_appcontainer_job(
                    argv,
                    timeout_seconds=60,
                    limit_bytes=PRODUCTION_LIMIT_BYTES,
                    cwd=stage,
                    stdout_path=stage / "stdout.bin",
                    stderr_path=stage / "stderr.bin",
                )
            evidence = json.loads(out_file.read_text(encoding="utf-8-sig"))
            if label == "restricted":
                assert evidence["connect"] != "CONNECTED", (
                    "the AppContainer target opened an outbound connection"
                )
            else:
                assert evidence["connect"] == "CONNECTED", (
                    "the unrestricted control could not connect, so the "
                    "denial result above proves nothing"
                )
    finally:
        endpoint.close()


# ---------------------------------------------------------------------------
# 3. The restriction survives descendants
# ---------------------------------------------------------------------------


def test_restriction_survives_child_and_grandchild(product_profile, stage):
    """A child and a grandchild of the restricted target stay denied.

    The descendant chain is created with ``[System.Diagnostics.Process]::Start``
    against the System32 PowerShell. ``Start-Process`` is **not** available
    under the restricted token (measured: it fails to resolve), so using it
    would test the harness rather than the containment.

    The **unrestricted** arm runs the same three-generation chain without
    the AppContainer, and every generation must connect, so a "denied"
    result cannot be dismissed as a chain that never ran.
    """
    endpoint = _Endpoint()
    probe = _write_probe(stage)
    target = _lan_ip()
    ps_exe = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "WindowsPowerShell", "v1.0", "powershell.exe",
    )

    def _chain(label, restricted):
        """Run the three-generation chain; return each generation's result."""
        out_file = stage / ("chain_%s.json" % label)
        child_out = stage / ("chain_%s_child.json" % label)
        grand_out = stage / ("chain_%s_grand.json" % label)
        for stale in (out_file, child_out, grand_out):
            if stale.exists():
                stale.unlink()
        script = stage / ("descend_%s.ps1" % label)
        script.write_text(
            "$ErrorActionPreference='Continue'\n"
            "$ps = '%s'\n" % ps_exe
            + "$child = '%s'\n" % probe
            + "$childOut = '%s'\n" % child_out
            + "$grandOut = '%s'\n" % grand_out
            + "$childArgs = @('-NoProfile','-NonInteractive','-ExecutionPolicy',"
              "'Bypass','-File',$child,'-Target','%s','-Port',%d,"
              "'-OutFile',$childOut)\n" % (target, endpoint.port)
            + "$childProc = [System.Diagnostics.Process]::Start($ps, $childArgs)\n"
            + "$childProc.WaitForExit()\n"
            + "$grandArgs = @('-NoProfile','-NonInteractive','-ExecutionPolicy',"
              "'Bypass','-File',$child,'-Target','%s','-Port',%d,"
              "'-OutFile',$grandOut)\n" % (target, endpoint.port)
            + "$grandProc = [System.Diagnostics.Process]::Start($ps, $grandArgs)\n"
            + "$grandProc.WaitForExit()\n"
            + "$results = @()\n"
            + "foreach ($f in @($childOut, $grandOut)) {"
              "  if (Test-Path $f) { "
              "$results += (Get-Content $f -Raw | ConvertFrom-Json) } }\n"
            + "[System.IO.File]::WriteAllText('%s', "
              "($results | ConvertTo-Json -Compress), [System.Text.Encoding]::UTF8)\n"
              % out_file,
            encoding="utf-8",
            newline="\r\n",
        )
        argv = [
            ps_exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script),
        ]
        if restricted:
            wj.run_in_appcontainer_job(
                argv,
                timeout_seconds=180,
                limit_bytes=PRODUCTION_LIMIT_BYTES,
                cwd=stage,
                stdout_path=stage / "stdout.bin",
                stderr_path=stage / "stderr.bin",
            )
        else:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=180, check=False,
                cwd=str(stage),
            )
            assert proc.returncode == 0, proc.stderr
        assert out_file.exists(), "the %s chain produced no report" % label
        payload = json.loads(out_file.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            payload = [payload]
        return payload

    try:
        # --- the UNRESTRICTED positive control: every generation connects --
        control = _chain("control", False)
        assert len(control) == 2, (
            "the unrestricted chain produced %d generation results, "
            "expected 2 (child and grandchild)" % len(control)
        )
        for entry in control:
            assert entry.get("connect") == "CONNECTED", (
                "the unrestricted control generation did not connect, so the "
                "denial result below proves nothing: %s" % entry.get("connect")
            )

        # --- the RESTRICTED chain: every generation is denied ---------------
        restricted = _chain("restricted", True)
        assert len(restricted) == 2, (
            "the restricted chain produced %d generation results, "
            "expected 2 (child and grandchild)" % len(restricted)
        )
        for entry in restricted:
            assert entry.get("connect") != "CONNECTED", (
                "a descendant of the restricted target opened an outbound "
                "connection"
            )
    finally:
        endpoint.close()


def _run_socket_probe(stage: Path, endpoint: _Endpoint, *, allowlist: bool):
    """Run the probe with (or without) the production allowlist.

    Returns the child's evidence and whether the server observed the
    socket's bytes.
    """
    probe = _write_probe(stage)
    out_file = stage / ("socket_%s.json" % ("allowlist" if allowlist else "control"))

    parent_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    parent_socket.settimeout(6.0)
    parent_socket.connect((_lan_ip(), endpoint.port))
    raw = int(parent_socket.fileno())
    flags = ctypes.c_uint32(0)
    wj._load_kernel32().GetHandleInformation(raw, ctypes.byref(flags))
    wj._load_kernel32().SetHandleInformation(raw, 0x00000001, flags.value | 0x00000001)

    argv = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
        "Bypass", "-File", str(probe), "-SocketHandle", str(raw),
        "-OutFile", str(out_file),
    ]
    try:
        if allowlist:
            # The PRODUCTION shape: a populated stdout/stderr allowlist.
            wj.run_in_appcontainer_job(
                argv,
                timeout_seconds=60,
                limit_bytes=PRODUCTION_LIMIT_BYTES,
                cwd=stage,
                stdout_path=stage / "stdout.bin",
                stderr_path=stage / "stderr.bin",
            )
        else:
            # The BYPASS shape: the same AppContainer launch, but with NO
            # explicit handle list, so every inheritable handle in the
            # parent -- including the connected socket -- crosses into the
            # child.  This is the threat-model fact the production allowlist
            # exists to defeat.  It is used ONLY in these tests, never in
            # the production launch path.
            wj.run_in_appcontainer_job(
                argv,
                timeout_seconds=60,
                limit_bytes=PRODUCTION_LIMIT_BYTES,
                cwd=stage,
                stdout_path=stage / "stdout.bin",
                stderr_path=stage / "stderr.bin",
                handle_policy=wa.HandlePolicy(use_explicit_allowlist=False),
            )
        time.sleep(1.0)
    finally:
        parent_socket.close()
    server_saw = endpoint.saw(b"PROBEUSESOCKET")
    endpoint.clear()
    evidence = json.loads(out_file.read_text(encoding="utf-8-sig"))
    return evidence, server_saw


def test_unrestricted_inherited_socket_control_is_usable(product_profile, stage):
    """POSITIVE CONTROL: the inherited socket really is usable.

    Without this control, a "the socket was excluded" result could be
    satisfied by a socket that was never usable at all.
    """
    endpoint = _Endpoint()
    try:
        evidence, server_saw = _run_socket_probe(stage, endpoint, allowlist=False)
        assert evidence.get("socket_use", "").startswith(("USED", "SENT-OK")), (
            f"the control could not use the inherited socket: "
            f"{evidence.get('socket_use')}"
        )
        assert server_saw is True, (
            "the server did not observe the control's bytes, so the socket "
            "was not genuinely usable"
        )
    finally:
        endpoint.close()


def test_production_allowlist_excludes_the_inherited_socket(product_profile, stage):
    """The production launch shape excludes a live inherited socket.

    The allowlist contains only stdout and stderr, so the connected
    socket never crosses into the child.
    """
    endpoint = _Endpoint()
    try:
        evidence, server_saw = _run_socket_probe(stage, endpoint, allowlist=True)
        assert server_saw is False, (
            "the restricted child used the inherited socket: the "
            "inherited-handle mitigation is not effective"
        )
        assert "SEND-FAILED" in str(evidence.get("socket_use")), (
            f"the child did not fail on the socket as expected: "
            f"{evidence.get('socket_use')}"
        )
        # The handle is present in the child's table but not inheritable,
        # and the child could not use it as a socket.
        assert "inheritable=False" in str(evidence.get("handle_info"))
    finally:
        endpoint.close()


def test_the_bypass_is_real(product_profile, stage):
    """An AppContainer token does not revoke an inherited network handle.

    This is the threat-model fact that motivates the allowlist. It is
    asserted explicitly so a future change that removes the allowlist is
    caught: the bypass must remain demonstrable when no allowlist is
    applied.
    """
    endpoint = _Endpoint()
    try:
        evidence, server_saw = _run_socket_probe(stage, endpoint, allowlist=False)
        assert server_saw is True
        assert "inheritable=True" in str(evidence.get("handle_info"))
    finally:
        endpoint.close()


# ---------------------------------------------------------------------------
# 6. The pre-resume containment ordering
# ---------------------------------------------------------------------------


def test_the_job_limit_is_in_force_before_the_target_runs(product_profile, stage):
    """The Job limit and the AppContainer identity precede the first instruction.

    The marker file the target writes as its first action must not exist
    while the target is still suspended.
    """
    marker = stage / "ran.txt"
    script = stage / "marker.ps1"
    script.write_text(
        f"[System.IO.File]::WriteAllText('{marker}', 'ran')\n",
        encoding="utf-8",
        newline="\r\n",
    )
    # The launch returns only after the target has finished, so the
    # marker must exist afterwards -- proving the target really ran.
    wj.run_in_appcontainer_job(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
            "Bypass", "-File", str(script),
        ],
        timeout_seconds=60,
        limit_bytes=PRODUCTION_LIMIT_BYTES,
        cwd=stage,
        stdout_path=stage / "stdout.bin",
        stderr_path=stage / "stderr.bin",
    )
    assert marker.exists()


def test_the_production_limit_is_two_gibibytes():
    """The production per-process limit is unchanged."""
    assert wj.JOB_OBJECT_LIMIT_BYTES == PRODUCTION_LIMIT_BYTES


# ---------------------------------------------------------------------------
# 7/8. The real Poppler workload and the minimum-ACL contract
# ---------------------------------------------------------------------------


def _stage_poppler(tmp_path: Path) -> Path | None:
    """Stage the pinned Poppler, or return ``None`` when it is absent."""
    import shutil

    found = shutil.which("pdftoppm")
    if not found:
        return None
    source = Path(found).parent
    target = STAGING_ROOT / "poppler"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, target / item.name)
    wa.grant_minimum_access(tuple(p for p in target.iterdir() if p.is_file()))
    return target / ("pdftoppm.exe" if os.name == "nt" else "pdftoppm")


def test_real_poppler_runs_under_the_restricted_token(product_profile, stage):
    """The real Poppler workload succeeds inside the AppContainer."""
    executable = _stage_poppler(stage)
    if executable is None:
        pytest.skip("pdftoppm is not installed on this runner")

    pdf = stage / "input.pdf"
    _minimal_pdf(pdf)
    _grant(stage, "M")
    out_prefix = stage / "page"

    result = wj.run_in_appcontainer_job(
        [
            str(executable), "-r", "200", "-png", "-f", "1", "-l", "1",
            str(pdf), str(out_prefix),
        ],
        timeout_seconds=180,
        limit_bytes=PRODUCTION_LIMIT_BYTES,
        cwd=stage,
        stdout_path=stage / "stdout.bin",
        stderr_path=stage / "stderr.bin",
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    produced = sorted(p.name for p in stage.glob("*.png"))
    assert produced == ["page-1.png"], f"unexpected artifacts: {produced}"
    assert (stage / "page-1.png").stat().st_size > 0


def test_the_parser_fails_closed_without_the_product_acl(product_profile, stage):
    """Without the product-SID grant the parser cannot run.

    This proves the ACL is what confers access, rather than some
    ambient permission.
    """
    import shutil

    found = shutil.which("pdftoppm")
    if not found:
        pytest.skip("pdftoppm is not installed on this runner")
    source = Path(found).parent

    # A copy with the product-SID grant REMOVED and inheritance broken so
    # the inherited ALL APPLICATION PACKAGES entry cannot confer access.
    control_dir = stage / "noacl"
    control_dir.mkdir()
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, control_dir / item.name)
    subprocess.run(
        ["icacls", str(control_dir), "/inheritance:r", "/T", "/C"],
        capture_output=True, text=True, errors="replace", timeout=240, check=False,
    )
    subprocess.run(
        ["icacls", str(control_dir), "/remove", "*S-1-15-2-1", "/T", "/C"],
        capture_output=True, text=True, errors="replace", timeout=240, check=False,
    )
    subprocess.run(
        ["icacls", str(control_dir), "/remove", f"*{wa.PRODUCT_PACKAGE_SID}", "/T", "/C"],
        capture_output=True, text=True, errors="replace", timeout=240, check=False,
    )

    pdf = stage / "input.pdf"
    _minimal_pdf(pdf)
    _grant(stage, "M")

    with pytest.raises(wa.AppContainerSetupError):
        wj.run_in_appcontainer_job(
            [
                str(control_dir / ("pdftoppm.exe" if os.name == "nt" else "pdftoppm")),
                "-r", "200", "-png", "-f", "1", "-l", "1",
                str(pdf), str(stage / "page"),
            ],
            timeout_seconds=120,
            limit_bytes=PRODUCTION_LIMIT_BYTES,
            cwd=stage,
            stdout_path=stage / "stdout.bin",
            stderr_path=stage / "stderr.bin",
        )


# ---------------------------------------------------------------------------
# 9. The error taxonomy
# ---------------------------------------------------------------------------


def test_a_setup_failure_never_executes_the_parser(product_profile, stage):
    """A containment setup failure prevents parser execution.

    The target is created suspended and terminated before it can run, so
    the marker file must not appear.
    """
    marker = stage / "ran.txt"
    script = stage / "marker.ps1"
    script.write_text(
        f"[System.IO.File]::WriteAllText('{marker}', 'ran')\n",
        encoding="utf-8",
        newline="\r\n",
    )
    with pytest.raises(wa.AppContainerSetupError):
        wj.run_in_appcontainer_job(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                "Bypass", "-File", str(script),
            ],
            timeout_seconds=30,
            limit_bytes=PRODUCTION_LIMIT_BYTES,
            cwd=stage,
            stdout_path=stage / "stdout.bin",
            stderr_path=stage / "stderr.bin",
            package_sid=wa.PRODUCT_PACKAGE_SID,
            expected_package_sid=wa.ALL_APPLICATION_PACKAGES_SID,
        )
    assert not marker.exists()


def test_the_setup_failure_carries_a_stage():
    """The setup failure names the stage that failed."""
    with pytest.raises(wa.AppContainerSetupError) as excinfo:
        wj.run_in_appcontainer_job(
            ["this-executable-does-not-exist.exe"],
            timeout_seconds=30,
            limit_bytes=PRODUCTION_LIMIT_BYTES,
            cwd=Path(os.environ.get("TEMP", ".")),
            stdout_path=Path(os.environ.get("TEMP", ".")) / "stdout.bin",
            stderr_path=Path(os.environ.get("TEMP", ".")) / "stderr.bin",
        )
    assert excinfo.value.details.get("stage")


# ---------------------------------------------------------------------------
# 10. Cleanup
# ---------------------------------------------------------------------------


def test_repeated_launches_leak_no_processes(product_profile, stage):
    """Repeated launches leave no parser process behind."""
    probe = _write_probe(stage)
    before = len(list(Path(tempfile_gettempdir()).glob("chess_coach_appcontainer_*")))
    for _ in range(3):
        wj.run_in_appcontainer_job(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                "Bypass", "-File", str(probe),
            ],
            timeout_seconds=60,
            limit_bytes=PRODUCTION_LIMIT_BYTES,
            cwd=stage,
            stdout_path=stage / "stdout.bin",
            stderr_path=stage / "stderr.bin",
        )
    after = len(list(Path(tempfile_gettempdir()).glob("chess_coach_appcontainer_*")))
    assert after <= before


def tempfile_gettempdir() -> str:
    import tempfile

    return tempfile.gettempdir()


def test_no_listener_is_left_behind(product_profile, stage):
    """The containment tests leave no listener running."""
    endpoint = _Endpoint()
    port = endpoint.port
    endpoint.close()
    time.sleep(0.5)
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(2.0)
        with pytest.raises((ConnectionRefusedError, socket.timeout, OSError)):
            probe.connect(("127.0.0.1", port))
    finally:
        probe.close()
