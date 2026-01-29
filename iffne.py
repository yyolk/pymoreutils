#!/usr/bin/env python3
import sys
import subprocess
import shutil
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="iffne - run a command if the standard input is not empty",
        usage="%(prog)s [-n] command [args...]",
    )
    parser.add_argument(
        "-n",
        "--reverse",
        action="store_true",
        help="Reverse operation: Run command if stdin IS empty.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run")

    args = parser.parse_args()

    # argparse REMAINDER puts the command and its args into a list.
    # However, if no command is provided, it might be empty.
    if not args.command:
        parser.print_usage()
        sys.exit(1)

    cmd_list = args.command

    # 1. Try to read a chunk from stdin.
    # We use buffer.read(1) to block until at least one byte is available
    # or EOF is reached. Using a larger buffer size is allowed (C version
    # uses BUFSIZ), but 1 byte minimizes latency for the check.
    try:
        initial_chunk = sys.stdin.buffer.read(1)
    except Exception as e:
        sys.stderr.write(f"iffne: Error reading stdin: {e}\n")
        sys.exit(1)

    is_empty = len(initial_chunk) == 0

    # 2. Logic Handler
    if args.reverse:
        # MODE: Run if EMPTY
        if is_empty:
            # Stdin is empty, run the command.
            # We don't need to pass stdin to it since it's empty.
            try:
                subprocess.check_call(cmd_list)
            except subprocess.CalledProcessError as e:
                sys.exit(e.returncode)
        else:
            # Stdin is NOT empty.
            # We must pass the data through to stdout (act like cat),
            # and NOT run the command.
            sys.stdout.buffer.write(initial_chunk)
            shutil.copyfileobj(sys.stdin.buffer, sys.stdout.buffer)

    else:
        # MODE: Run if NOT EMPTY (Default)
        if is_empty:
            # Stdin is empty, do nothing, exit success.
            sys.exit(0)
        else:
            # Stdin has data. Run the command and pipe data to it.
            try:
                # We open the subprocess with a pipe for stdin so we can
                # inject the initial_chunk we already read.
                proc = subprocess.Popen(cmd_list, stdin=subprocess.PIPE)
            except OSError as e:
                sys.stderr.write(f"iffne: Failed to execute '{cmd_list[0]}': {e}\n")
                sys.exit(1)

            try:
                # Write the "peeked" byte
                proc.stdin.write(initial_chunk)

                # Using shutil to efficiently stream the rest of stdin to the process
                # copyfileobj reads in chunks (default 64KB in Py3)
                shutil.copyfileobj(sys.stdin.buffer, proc.stdin)

                # Close stdin to signal EOF to the child
                proc.stdin.close()

                # Wait for child to exit
                ret_code = proc.wait()
                sys.exit(ret_code)

            except BrokenPipeError:
                # Child closed its stdin early; this is normal (e.g. `yes | ifne head`)
                # We just wait for it to finish.
                ret_code = proc.wait()
                sys.exit(ret_code)


if __name__ == "__main__":
    main()
