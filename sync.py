import argparse
import asyncio

from app.sync import synchronize


def main():
    parser = argparse.ArgumentParser(description="Synchronize Strava activities")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--full-history", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(synchronize(args.retry_failed, args.local_only, args.full_history))
    print("\nSynchronization summary:")
    print(result)


if __name__ == "__main__":
    main()
