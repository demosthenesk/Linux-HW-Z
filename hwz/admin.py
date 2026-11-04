"""Client side of the administrator helper (pkexec + helper_root.py)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading

from .probes import dmi, spd

HERE = os.path.dirname(os.path.abspath(__file__))


class AdminSession:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.smbios: dict | None = None
        self.spd: list[dict] = []
        self.serials: dict = {}
        self.power: dict[str, float] = {}
        self.vcore: dict[str, float] = {}
        self.error = ""
        self.got_info = False
        self.ready = threading.Event()
        self._tmp = None

    @property
    def active(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @staticmethod
    def python() -> str:
        for p in ("/usr/bin/python3", "/bin/python3"):
            if os.path.exists(p):
                return p
        return ""

    def start(self, cpus: list[int], interval: float = 1.0) -> bool:
        """Ask for the password (polkit).  Returns False if pkexec is missing."""
        pk = shutil.which("pkexec") or ("pkexec" if os.environ.get("HWZ_ADMIN_NO_PKEXEC") else None)
        py = self.python()
        if not pk or not py:
            self.error = "pkexec or /usr/bin/python3 is not available"
            self.ready.set()
            return False
        # copy the helper out of the AppImage mount: root cannot read a user's FUSE mount
        self._tmp = tempfile.mkdtemp(prefix="hwz-helper-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
        dst = os.path.join(self._tmp, "linux-hw-z-helper.py")
        shutil.copyfile(os.path.join(HERE, "helper_root.py"), dst)
        os.chmod(dst, 0o644)
        cmd = [pk, py, "-I", dst, "--interval", str(interval), "--cpus", ",".join(map(str, cpus))]
        if os.environ.get("HWZ_ADMIN_NO_PKEXEC") and os.geteuid() == 0:
            cmd = cmd[1:]  # test hook: already root, run the helper directly
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, bufsize=1)
        except OSError as e:
            self.error = str(e)
            self.ready.set()
            return False
        threading.Thread(target=self._reader, daemon=True).start()
        return True

    def _reader(self):
        p = self.proc
        assert p and p.stdout
        for line in p.stdout:
            if line.startswith("I "):
                try:
                    info = json.loads(line[2:])
                    raw = base64.b64decode(info.get("dmi") or "")
                    self.smbios = dmi.parse_table(raw) if raw else None
                    mods = []
                    for addr, b64 in sorted(info.get("spd", {}).items()):
                        dec = spd.decode(base64.b64decode(b64))
                        if dec:
                            dec["address"] = addr
                            mods.append(dec)
                    self.spd = mods
                    self.serials = info.get("serials", {})
                    self.got_info = True
                except Exception as e:  # malformed output should never crash the UI
                    self.error = f"helper output: {e}"
                self.ready.set()
            elif line.startswith("S "):
                try:
                    s = json.loads(line[2:])
                    self.power = s.get("power", {})
                    self.vcore = s.get("vcore", {})
                except ValueError:
                    pass
        rc = p.wait()
        if not self.ready.is_set():
            err = (p.stderr.read() if p.stderr else "").strip()
            self.error = {126: "Authentication was cancelled.", 127: "Authentication failed."}.get(rc, err or
                                                                                                   f"exit code {rc}")
            self.ready.set()
        self._cleanup()

    def _cleanup(self):
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()  # helper exits on EOF
            except OSError:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        self._cleanup()
