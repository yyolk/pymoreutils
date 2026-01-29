#!/usr/bin/env python3
import sys
import time
import textwrap
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="tstamp - timestamp standard input",
        epilog=textwrap.dedent("""
            Format:
              The optional format argument controls the timestamp. 
              It uses standard strftime directives (e.g. "%H:%M:%S").
              Default is "%b %d %H:%M:%S".
        """),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-i",
        "--incremental",
        action="store_true",
        help="Print time elapsed since the last timestamp.",
    )
    group.add_argument(
        "-s",
        "--since-start",
        action="store_true",
        help="Print time elapsed since the start of the program.",
    )

    parser.add_argument(
        "-m",
        "--monotonic",
        action="store_true",
        help="Use the system monotonic clock (immune to time changes).",
    )
    parser.add_argument(
        "format", nargs="?", default=None, help="Format string for the timestamp."
    )

    args = parser.parse_args()

    # Default format changes based on mode
    if args.format:
        fmt = args.format
        # FEATURE: Strip leading '+' to match 'date' utility behavior
        if fmt.startswith("+"):
            fmt = fmt[1:]
    else:
        if args.incremental or args.since_start:
            fmt = "%H:%M:%S"
        else:
            fmt = "%b %d %H:%M:%S"

    # Select the clock source
    if args.monotonic:
        get_time = time.monotonic
    else:
        get_time = time.time

    start_time = get_time()
    last_time = start_time
    stdin_iter = sys.stdin.buffer

    try:
        for line_bytes in stdin_iter:
            current_time = get_time()

            if args.incremental:
                delta = current_time - last_time
                last_time = current_time
                ts_struct = time.gmtime(delta)
                ts_str = time.strftime(fmt, ts_struct)

            elif args.since_start:
                delta = current_time - start_time
                ts_struct = time.gmtime(delta)
                ts_str = time.strftime(fmt, ts_struct)

            else:
                ts_struct = time.localtime(current_time)
                ts_str = time.strftime(fmt, ts_struct)

            line_str = line_bytes.decode("utf-8", "replace").rstrip("\n")
            print(f"{ts_str} {line_str}", flush=True)

    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
