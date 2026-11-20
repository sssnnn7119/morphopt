"""Run a Qt/VTK capture command on a private Linux display."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def run_hidden(command: list[str]) -> None:
    """Give all Qt windows and child renderers the same isolated X11 display."""
    env = {key: value for key, value in os.environ.items() if key not in {
        "DISPLAY", "WAYLAND_DISPLAY", "SESSION_MANAGER", "DBUS_SESSION_BUS_ADDRESS",
        "XAUTHORITY", "QT_QPA_PLATFORM", "XDG_SESSION_TYPE",
    }}
    client_env = dict(QT_QPA_PLATFORM="xcb", XDG_SESSION_TYPE="x11", QT_SCALE_FACTOR="1")
    if shutil.which("xvfb-run") and shutil.which("Xvfb") and shutil.which("xauth"):
        subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1920x1200x24", *command],
                       env=env | client_env, check=True)
        return
    if not (sys.platform.startswith("linux") and all(shutil.which(tool) for tool in
            ("kwin_wayland", "Xwayland", "dbus-run-session"))):
        raise SystemExit("Headless capture requires Xvfb with xvfb-run and xauth, or "
                         "KWin with Xwayland and dbus-run-session. Use --visible for a desktop session.")
    with TemporaryDirectory(prefix="morphopt-display-") as tmp:
        directory = Path(tmp)
        for name, key in (("runtime", "XDG_RUNTIME_DIR"), ("config", "XDG_CONFIG_HOME"),
                          ("data", "XDG_DATA_HOME"), ("cache", "XDG_CACHE_HOME")):
            path = directory / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        # KWin accepts one command string and does not propagate the client's exit code.
        # A short launcher also preserves spaces in repository and archive names.
        launcher = directory / "capture"
        status = directory / "status"
        client = ["env", *(f"{k}={v}" for k, v in client_env.items()), *command]
        launcher.write_text("#!/bin/sh\n" + shlex.join(client) + "\n" +
                            'echo "$?" > ' + shlex.quote(str(status)) + "\n", encoding="utf-8")
        launcher.chmod(0o700)
        # The compositor needs a session bus, but not desktop services. In particular,
        # the document portal would mount a FUSE filesystem inside the temporary runtime.
        bus = directory / "bus.conf"
        bus.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                       '<policy context="default"><allow own="*"/><allow send_destination="*"/>'
                       '<allow receive_sender="*"/>'
                       '</policy></busconfig>', encoding="utf-8")
        subprocess.run(["dbus-run-session", f"--config-file={bus}", "--", "kwin_wayland", "--virtual", "--xwayland",
                        "--no-lockscreen", "--no-global-shortcuts", "--no-kactivities",
                        "--width", "1920", "--height", "1200", "--exit-with-session",
                        str(launcher)], env=env, check=True)
        if not status.is_file() or status.read_text().strip() != "0":
            raise SystemExit("The virtual capture session did not finish successfully.")
