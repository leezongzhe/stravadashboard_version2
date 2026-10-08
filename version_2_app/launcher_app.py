"""Windows desktop launcher for the local Streamlit dashboard."""

import argparse
import asyncio
import contextlib
import io
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


# PyInstaller's windowed bootloader sets these streams to None. Streamlit and
# its logging stack expect file-like objects even when the launcher is hidden.
# Pointing them at the Windows null device keeps the packaged server alive
# without opening a console window.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _bundle_path(filename):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / filename


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def serve_dashboard(port):
    from streamlit.web import bootstrap

    options = {
        "global_developmentMode": False,
        "server_address": "127.0.0.1",
        "server_port": int(port),
        "server_headless": True,
        "browser_gatherUsageStats": False,
        "server_fileWatcherType": "none",
    }
    bootstrap.load_config_options(options)
    bootstrap.run(
        str(_bundle_path("dashboard.py")),
        False,
        [],
        options,
    )


def _server_command(port):
    if getattr(sys, "frozen", False):
        server_executable = Path(sys.executable).with_name("StravaDashboardServer.exe")
        return [str(server_executable), "--serve-dashboard", "--port", str(port)]
    return [sys.executable, str(Path(__file__).resolve()), "--serve-dashboard", "--port", str(port)]


def _wait_for_server(url, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


class QueueWriter(io.TextIOBase):
    def __init__(self, messages):
        self.messages = messages

    def write(self, value):
        if value and value.strip():
            self.messages.put(("log", value.strip()))
        return len(value)

    def flush(self):
        return None


class WindowsLauncher:
    def __init__(self, dashboard_only=False):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = tk.Tk()
        self.root.title("Strava Dashboard")
        self.root.geometry("620x390")
        self.root.minsize(540, 340)
        self.root.configure(bg="#eef4f1")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.messages = queue.Queue()
        self.server = None
        self.url = None

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Hero.TLabel", background="#eef4f1", foreground="#17352b", font=("Segoe UI Semibold", 24))
        style.configure("Body.TLabel", background="#eef4f1", foreground="#587067", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(18, 10))
        style.configure("TProgressbar", troughcolor="#dfe9e4", background="#e95735", borderwidth=0)

        frame = ttk.Frame(self.root, padding=30)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Strava Dashboard", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Private, local training analytics", style="Body.TLabel").pack(anchor="w", pady=(2, 24))
        self.status = tk.StringVar(value="Preparing application…")
        ttk.Label(frame, textvariable=self.status, style="Body.TLabel", wraplength=540).pack(anchor="w")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 18))
        self.progress.start(12)
        self.log = tk.Text(frame, height=7, relief="flat", bg="#ffffff", fg="#365448", padx=12, pady=10, font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(16, 0))
        self.open_button = ttk.Button(controls, text="Open dashboard", style="Accent.TButton", command=self.open_dashboard, state="disabled")
        self.open_button.pack(side="right")
        ttk.Button(controls, text="Close", command=self.close).pack(side="right", padx=(0, 10))

        initial_download_limit = None
        if not dashboard_only:
            from app.database import get_app_setting, initialize_database
            from app.sync import INITIAL_DOWNLOAD_SETUP_SETTING

            initialize_database()
            if get_app_setting(INITIAL_DOWNLOAD_SETUP_SETTING) != "true":
                initial_download_limit = self._ask_initial_download_limit()
                if initial_download_limit is False:
                    dashboard_only = True
                    self._append("First-time synchronization cancelled; opening the dashboard without syncing.")

        self.root.after(100, self._drain_messages)
        threading.Thread(
            target=self._prepare,
            args=(dashboard_only, initial_download_limit),
            daemon=True,
        ).start()

    def _ask_initial_download_limit(self):
        """Ask once whether initial setup should download all or the latest N."""
        dialog = self.tk.Toplevel(self.root)
        dialog.title("First synchronization")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg="#eef4f1")
        dialog.grab_set()

        result = {"value": False}
        mode = self.tk.StringVar(value="all")
        count = self.tk.StringVar(value="")
        error = self.tk.StringVar(value="")

        panel = self.tk.Frame(dialog, bg="#ffffff", padx=28, pady=24)
        panel.pack(padx=18, pady=18, fill="both", expand=True)
        self.tk.Label(
            panel,
            text="Choose your first download",
            bg="#ffffff",
            fg="#17352b",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")
        self.tk.Label(
            panel,
            text=(
                "This is asked once. Future launches inspect only your newest Strava page.\n"
                "If your number is larger than the available history, every activity is downloaded."
            ),
            bg="#ffffff",
            fg="#587067",
            justify="left",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(5, 18))

        all_button = self.tk.Radiobutton(
            panel,
            text="Download all available activities",
            variable=mode,
            value="all",
            bg="#ffffff",
            activebackground="#ffffff",
            fg="#17352b",
            font=("Segoe UI", 10),
        )
        all_button.pack(anchor="w", pady=(0, 10))

        number_row = self.tk.Frame(panel, bg="#ffffff")
        number_row.pack(anchor="w", fill="x")
        self.tk.Radiobutton(
            number_row,
            text="Download the latest",
            variable=mode,
            value="number",
            bg="#ffffff",
            activebackground="#ffffff",
            fg="#17352b",
            font=("Segoe UI", 10),
        ).pack(side="left")
        count_entry = self.tk.Entry(
            number_row,
            textvariable=count,
            width=9,
            relief="solid",
            bd=1,
            font=("Segoe UI", 10),
        )
        count_entry.pack(side="left", padx=8)
        self.tk.Label(
            number_row,
            text="activities",
            bg="#ffffff",
            fg="#17352b",
            font=("Segoe UI", 10),
        ).pack(side="left")
        count_entry.bind("<FocusIn>", lambda _event: mode.set("number"))

        self.tk.Label(
            panel,
            textvariable=error,
            bg="#ffffff",
            fg="#b42318",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(10, 0))

        def continue_setup():
            if mode.get() == "all":
                result["value"] = "all"
            else:
                try:
                    requested = int(count.get().strip())
                    if requested < 1:
                        raise ValueError
                except ValueError:
                    error.set("Enter a whole number of 1 or greater.")
                    count_entry.focus_set()
                    return
                result["value"] = requested
            dialog.destroy()

        def cancel_setup():
            result["value"] = False
            dialog.destroy()

        buttons = self.tk.Frame(panel, bg="#ffffff")
        buttons.pack(fill="x", pady=(18, 0))
        self.tk.Button(
            buttons,
            text="Continue",
            command=continue_setup,
            bg="#e95735",
            fg="#ffffff",
            activebackground="#cc4428",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI Semibold", 10),
        ).pack(side="right")
        self.tk.Button(
            buttons,
            text="Cancel",
            command=cancel_setup,
            bg="#edf2ef",
            fg="#365448",
            activebackground="#dfe9e4",
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 10),
        ).pack(side="right", padx=(0, 8))

        dialog.protocol("WM_DELETE_WINDOW", cancel_setup)
        dialog.bind("<Return>", lambda _event: continue_setup())
        dialog.bind("<Escape>", lambda _event: cancel_setup())
        dialog.update_idletasks()
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_y() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        self.root.wait_window(dialog)
        return result["value"]

    def _append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _prepare(self, dashboard_only, initial_download_limit=None):
        try:
            if not dashboard_only:
                self.messages.put(("status", "Synchronizing Strava activities… Complete first-time login in Chrome if requested."))
                from app.sync import synchronize
                writer = QueueWriter(self.messages)
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    result = asyncio.run(
                        synchronize(initial_download_limit=initial_download_limit)
                    )
                self.messages.put(("log", f"Synchronization complete: {result}"))
            else:
                self.messages.put(("log", "Synchronization skipped."))

            self.messages.put(("status", "Starting the local dashboard…"))
            port = _free_port()
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.server = subprocess.Popen(_server_command(port), creationflags=creation_flags)
            self.url = f"http://127.0.0.1:{port}"
            if not _wait_for_server(self.url):
                raise RuntimeError("The dashboard server did not become ready.")
            self.messages.put(("ready", self.url))
        except Exception as error:
            self.messages.put(("error", str(error)))

    def _drain_messages(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self._append(value)
                elif kind == "status":
                    self.status.set(value)
                elif kind == "ready":
                    self.progress.stop()
                    self.status.set("Dashboard ready. You can keep this window minimized while using it.")
                    self.open_button.configure(state="normal")
                    self.open_dashboard()
                elif kind == "error":
                    self.progress.stop()
                    self.status.set("Startup could not be completed.")
                    self._append(f"ERROR: {value}")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def open_dashboard(self):
        if self.url:
            webbrowser.open(self.url)

    def close(self):
        if self.server and self.server.poll() is None:
            self.server.terminate()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Strava Dashboard Windows app")
    parser.add_argument("--serve-dashboard", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dashboard-only", action="store_true", help="Open without synchronizing")
    parser.add_argument("--port", type=int, default=8501, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_dashboard:
        serve_dashboard(args.port)
    else:
        WindowsLauncher(args.dashboard_only).run()


if __name__ == "__main__":
    main()
