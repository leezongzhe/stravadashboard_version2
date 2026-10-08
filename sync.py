import argparse
import asyncio

from app.sync import synchronize


def main():
    parser = argparse.ArgumentParser(description="Synchronize Strava activities")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    initial = parser.add_mutually_exclusive_group()
    initial.add_argument("--initial-records", type=int, metavar="N")
    initial.add_argument("--download-all", action="store_true")
    args = parser.parse_args()
    initial_limit = "all" if args.download_all else args.initial_records
    result = asyncio.run(
        synchronize(args.retry_failed, args.local_only, initial_limit)
    )
    print("\nSynchronization summary:")
    print(result)


if __name__ == "__main__":
    main()
