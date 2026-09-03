import argparse
import asyncio
import importlib.util
import subprocess
import sys


REQUIRED_MODULES = ["numpy", "pandas", "playwright", "plotly", "pydeck", "streamlit"]


def check_dependencies():
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        print("Missing dependencies: " + ", ".join(missing))
        print("Run: python -m pip install -r requirements.txt")
        print("Then run: python -m playwright install chromium")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Strava Dashboard version 2")
    parser.add_argument("--dashboard-only", action="store_true", help="Skip synchronization")
    parser.add_argument("--local-only", action="store_true", help="Import local TCX files without opening Strava")
    parser.add_argument("--retry-failed", action="store_true", help="Retry unavailable and failed downloads")
    args = parser.parse_args()

    if not check_dependencies():
        raise SystemExit(1)

    if not args.dashboard_only:
        from app.sync import synchronize
        result = asyncio.run(synchronize(args.retry_failed, args.local_only))
        print(f"Synchronization completed: {result}")

    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "dashboard.py"],
        check=False,
    )


if __name__ == "__main__":
    main()

