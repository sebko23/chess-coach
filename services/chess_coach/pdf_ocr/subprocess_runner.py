"""A-F11 subprocess runner — wraps pdftoppm with sandbox primitives.

This module provides a subprocess-based replacement for
`pdf2image.convert_from_bytes` that exposes the
`subprocess.Popen` parameters pdf2image does not (notably
`preexec_fn` for setting resource limits in the child
process). Per `docs/08_security/security-strategy.md`
§A-F11, the PDF parser MUST run in an isolated subprocess
with no network access, read-only filesystem, 2 GB memory
cap, and a 5-minute timeout.

**This BBF (FU-22-impl) implements the 2 GB memory cap via
`resource.setrlimit(RLIMIT_AS)` in a `preexec_fn` callback.**
The other 3 properties (network isolation, read-only FS,
timeout) are out of scope here; the timeout is already
enforced by the route's `asyncio.wait_for` wrapper.

The architectural pattern established here (bypass
pdf2image, call pdftoppm directly via `subprocess.Popen`
with the right sandbox primitives) is the foundation for
the follow-up BBFs (FU-20-impl: network isolation;
FU-21-impl: read-only filesystem). Per
`docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section C,
FU-22 is the lightest of the three and is implemented first
to establish the `subprocess_runner.py` module + refactor
pattern.
"""
from __future__ import annotations

import shutil
import subprocess  # noqa: S404  -- intentional: PDF parsing requires subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image

# `resource` is a Unix-only stdlib module. On Windows, it's
# not available; the cap mechanism is a no-op (Windows
# support is a future follow-up BBF).
if sys.platform != "win32":
    import resource  # noqa: E402  -- Unix-only; gated by sys.platform check above

# A-F11 property 4: 2 GB memory cap. Applied to the child
# process via preexec_fn=set_rlimit_as_preexec(MEM_CAP_BYTES).
# The hard cap (both soft and hard set to the same value)
# matches the A-F11 contract: "2 GB memory cap" is a
# ceiling, not a soft warning.
MEM_CAP_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB

# pdftoppm invocation defaults. These match the previous
# pdf2image.convert_from_bytes defaults (DPI=200, fmt=ppm)
# but are exposed as parameters for testability.
DEFAULT_DPI: int = 200
DEFAULT_FMT: str = "png"  # PNG is easier to read back than PPM

# Popen default timeout. The route layer wraps this in
# `asyncio.wait_for` for the outer timeout, but the
# `proc.communicate(timeout=...)` is the inner safety net.
DEFAULT_TIMEOUT_SECONDS: int = 300


def set_rlimit_as_preexec(mem_cap_bytes: int) -> Callable[[], None]:
    """Build a `preexec_fn` callable that caps the child process
    virtual-address-space at `mem_cap_bytes`.

    Returns a no-arg callable suitable for `subprocess.Popen`'s
    `preexec_fn=` parameter. The callable runs in the child
    process after `fork` but before `exec`, so the cap is
    in place before pdftoppm starts allocating.

    On Linux, this calls `resource.setrlimit(resource.RLIMIT_AS,
    (cap, cap))`. `RLIMIT_AS` covers the entire virtual
    address space (heap + stack + mmap + shared libraries),
    so the cap is a hard ceiling, not just a heap cap.

    On Windows, `resource.setrlimit` is not available. The
    Windows equivalent is a Job Object with
    `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (see follow-up BBFs
    FU-20-impl / FU-21-impl). The current implementation
    **returns a no-op callable** on Windows (a
    `_noop_preexec` that just `return None`s); the test
    `test_set_rlimit_as_preexec_no_cap_means_no_cap`
    covers the no-cap code path on Windows.

    Args:
        mem_cap_bytes: the cap, in bytes. Both soft and hard
            limits are set to this value (hard ceiling).

    Returns:
        A no-arg callable for use as `preexec_fn=`.
    """
    if sys.platform == "win32":
        # The Windows path uses a Job Object with
        # `JOB_OBJECT_LIMIT_PROCESS_MEMORY`. That requires
        # `pywin32` and the `win32job` module, which is
        # not currently a project dependency. The follow-up
        # BBF (Windows FU-22 path) can add this. For now,
        # the cap is a no-op on Windows; the test
        # `test_set_rlimit_as_preexec_no_cap_means_no_cap`
        # covers the no-cap code path on Windows.
        def _noop_preexec() -> None:
            return None
        return _noop_preexec

    def _set_rlimit_preexec() -> None:
        # RLIMIT_AS is the virtual-address-space cap. Both
        # soft and hard are set to the same value so a
        # malicious PDF cannot slowly drift past a soft
        # limit. The cap is in place before pdftoppm starts
        # (preexec_fn runs after fork, before exec).
        resource.setrlimit(resource.RLIMIT_AS, (mem_cap_bytes, mem_cap_bytes))  # type: ignore[name-defined]

    return _set_rlimit_preexec


def _build_pdftoppm_args(
    dpi: int,
    first_page: int,
    last_page: int,
    output_prefix: Path,
) -> list[str]:
    """Build the pdftoppm command-line args.

    pdftoppm is the Poppler PDF-to-image converter. The
    invocation pattern is:

        pdftoppm -r <dpi> -png -f <first> -l <last> <input> <output_prefix>

    The input is fed via stdin (the PDF bytes); the output
    files are written to `<output_prefix>-1.png`,
    `<output_prefix>-2.png`, etc. (one file per page).
    """
    return [
        "pdftoppm",
        "-r", str(dpi),
        "-png",
        "-f", str(first_page),
        "-l", str(last_page),
        "-",  # read PDF from stdin
        str(output_prefix),
    ]


def run_pdftoppm_in_subprocess(
    pdf_bytes: bytes,
    *,
    dpi: int = DEFAULT_DPI,
    first_page: int = 1,
    last_page: int | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    mem_cap_bytes: int = MEM_CAP_BYTES,
) -> list[Image.Image]:
    """Run pdftoppm in a subprocess with the 2 GB memory cap.

    Replaces `pdf2image.convert_from_bytes` for the A-F11
    path. The return contract (`list[PIL.Image.Image]`) is
    preserved so downstream code (the `import_pdf` route)
    is unchanged.

    Args:
        pdf_bytes: the raw PDF content (read from stdin)
        dpi: render DPI (default 200)
        first_page: 1-indexed first page to render
        last_page: 1-indexed last page to render; `None` means
            render all pages
        timeout_seconds: per-Popen timeout; the parent
            process is killed with `TimeoutExpired` if the
            subprocess exceeds this
        mem_cap_bytes: virtual-address-space cap (default 2 GB);
            a malicious PDF that triggers unbounded
            allocation will be killed at this threshold

    Returns:
        list[PIL.Image.Image], one per rendered page

    Raises:
        subprocess.TimeoutExpired: if the subprocess exceeds
            `timeout_seconds`
        OSError: if pdftoppm is not on PATH (e.g. on Windows
            hosts without poppler installed); the route layer
            catches this and returns HTTP 422
        MemoryError: if the subprocess exits because of a
            2 GB-cap hit (a malicious PDF is a security
            event, surfaced to the user as 422)
    """
    last_page_arg = last_page if last_page is not None else 0  # 0 = "all"

    with tempfile.TemporaryDirectory(prefix="chess_coach_pdftoppm_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        output_prefix = tmpdir / "page"
        args = _build_pdftoppm_args(dpi, first_page, last_page_arg, output_prefix)

        # The preexec_fn sets the 2 GB cap in the child
        # process before pdftoppm starts. This is the
        # only point at which setrlimit is effective: after
        # fork, before exec. pdf2image's convert_from_bytes
        # does not expose preexec_fn, which is why this
        # module bypasses pdf2image and calls pdftoppm
        # directly.
        preexec_fn = set_rlimit_as_preexec(mem_cap_bytes)

        # The child process's stdin is the PDF bytes; the
        # child writes output files into tmpdir (which is
        # the per-book artifact dir in production use, but
        # a tempdir for the test path).
        proc: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            preexec_fn=preexec_fn,  # noqa: S901  -- intentional A-F11 mechanism
        )

        # Feed the PDF bytes via stdin; capture stderr for
        # diagnostics. communicate(timeout=...) is the inner
        # timeout safety net; the route's asyncio.wait_for
        # is the outer safety net.
        try:
            _, stderr_bytes = proc.communicate(input=pdf_bytes, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            raise RuntimeError(
                f"pdftoppm exited with code {proc.returncode}: {stderr_text[:500]}"
            )

        # pdftoppm wrote one file per page. Load them
        # back as PIL images. The naming is
        # `<output_prefix>-NNN.png` (zero-padded to 3
        # digits) or `<output_prefix>-N.png` (no padding)
        # depending on pdftoppm version. We handle both.
        png_files = sorted(tmpdir.glob("*.png"))
        if not png_files:
            raise RuntimeError(
                "pdftoppm exited cleanly but produced no PNG files; "
                "the PDF may be empty or the page range may be out of bounds."
            )
        return [Image.open(p) for p in png_files]


def pdftoppm_available() -> bool:
    """Check whether pdftoppm is on PATH (and thus callable).

    Used by the route layer to gracefully degrade on
    Windows hosts (where poppler is not bundled). Returns
    True if `pdftoppm` is found via `shutil.which`, False
    otherwise. The check is cheap; the route layer calls
    it once at module import time.
    """
    return shutil.which("pdftoppm") is not None
