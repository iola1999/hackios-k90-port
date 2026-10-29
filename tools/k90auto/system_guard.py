"""System image identity checks for make-payload.py, kept separate so a replay test can call them.

The two images under hackios-xnu-kernel/userland/ are 2.49 GB (iOS 16.5) and 4.93 GB (iOS 26), and
SYSTEM defaults to the 16.5 one. A payload that boots the 16.5 userland on the iOS 26 kernel reaches
launchd and dies at mach_ports_register with "could not set up inheritance port", which reads like an
IPC problem in the kernel (docs/analysis/2026-10-29-inheritance-port-16v26.md). These two bounds stop
that here instead of 400 seconds into a run.
"""

GIB = 1 << 30
SYSTEM_MIN = 4 * GIB
SYSTEM_MAX = 5 * GIB
MAX_INLINE_BYTES = 0xffffffff
DEFAULT_SYSTEM = "hackios-xnu-kernel/userland/system.apfs"
IOS26_SYSTEM = "hackios-xnu-kernel/userland/system26.apfs"


def identity_error(system_path, system_bytes, system_env, window):
    """Return the operator-facing message when this image cannot be the iOS 26 one, else None.

    system_env is the raw SYSTEM value (None when unset) so the message shows what was passed rather
    than what the default resolved to; window is the raw SYSTEM_WINDOW value ("" when unset).
    """
    if not SYSTEM_MIN <= system_bytes <= SYSTEM_MAX:
        return (f"system image {system_path} is {system_bytes} bytes, outside {SYSTEM_MIN}..{SYSTEM_MAX}: "
                f"SYSTEM={system_env if system_env is not None else '<unset>'}. The iOS 26 userland needs "
                f"SYSTEM={IOS26_SYSTEM}; the default is the iOS 16.5 image, which cannot run launchd on "
                f"this kernel")
    if system_bytes > MAX_INLINE_BYTES and not window:
        return (f"an image over {MAX_INLINE_BYTES} bytes needs SYSTEM_WINDOW: {system_path} is "
                f"{system_bytes} bytes and SYSTEM_WINDOW is unset; the loader transfers an image that "
                f"large by the chunked protocol")
    return None