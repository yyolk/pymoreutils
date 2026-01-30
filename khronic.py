#!/usr/bin/env python3
import sys
import subprocess
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="khronic - runs a command quietly unless it fails",
        usage="%(prog)s [-v] [-e] COMMAND...",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output: prints headers for STDOUT/STDERR and return value.",
    )
    parser.add_argument(
        "-e",
        "--stderr-trigger",
        action="store_true",
        help="Trigger output if anything is written to stderr, even if the command succeeds.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="The command to run.")

    args = parser.parse_args()

    if not args.command:
        parser.print_usage()
        sys.exit(1)

    try:
        result = subprocess.run(
            args.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except FileNotFoundError:
        sys.stderr.write(f"khronic: command not found: {args.command[0]}\n")
        sys.exit(127)
    except KeyboardInterrupt:
        sys.exit(130)

    # Determine if we should show output
    failed = result.returncode != 0
    stderr_triggered = args.stderr_trigger and len(result.stderr) > 0
    should_print = failed or stderr_triggered

    if should_print:
        if args.verbose:
            if result.stdout:
                sys.stdout.write("STDOUT:\n")
                sys.stdout.flush()
            sys.stdout.buffer.write(result.stdout)

            if result.stderr:
                sys.stdout.write("\nSTDERR:\n")
                sys.stdout.flush()
            sys.stderr.buffer.write(result.stderr)

            sys.stdout.write(f"\nRETVAL: {result.returncode}\n")
        else:
            sys.stdout.buffer.write(result.stdout)
            sys.stderr.buffer.write(result.stderr)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
