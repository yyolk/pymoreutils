#!/usr/bin/env python
import sys
import os
import argparse
import tempfile
import subprocess
import shlex


def main():
    parser = argparse.ArgumentParser(
        description="vype - edit pipe", usage="%(prog)s [--suffix=extension]"
    )
    parser.add_argument(
        "--suffix",
        help="Optional extension for the temp file (e.g., .csv, .json) "
        "to enable syntax highlighting in editors.",
    )
    args = parser.parse_args()

    # Handle suffix formatting
    suffix = args.suffix if args.suffix else ""
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix

    # 1. Read Input
    # We use binary mode for stdin/stdout to handle all data types safely without
    # encoding crashes.
    input_data = b""
    if not sys.stdin.isatty():
        try:
            input_data = sys.stdin.buffer.read()
        except Exception as e:
            sys.stderr.write(f"vype: Error reading stdin: {e}\n")
            sys.exit(1)

    # 2. Create Temp File
    # mkstemp returns a low-level file handle (int) and the absolute path (str)
    fd, temp_path = tempfile.mkstemp(suffix=suffix)

    try:
        # Write input data to the temp file
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(input_data)

        # 3. Determine Editor
        # Priority: EDITOR env var -> VISUAL env var -> 'vi'
        editor_cmd = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"

        # Split command string into list (e.g. "vim -c 'set noswapfile'" -> args)
        editor_args = shlex.split(editor_cmd)
        editor_args.append(temp_path)

        # 4. Spawn Editor
        # We must explicitly connect the editor's stdin/out/err to /dev/tty
        # because the script's stdin/out might be pipes.
        try:
            with open("/dev/tty", "r") as tty_in, open("/dev/tty", "w") as tty_out:
                subprocess.check_call(
                    editor_args, stdin=tty_in, stdout=tty_out, stderr=tty_out
                )
        except OSError:
            sys.stderr.write(
                "vype: Error opening /dev/tty. Are you running this interactively?\n"
            )
            sys.exit(1)
        except subprocess.CalledProcessError:
            sys.stderr.write(
                f"vype: Editor '{editor_cmd}' exited with non-zero status.\n"
            )
            sys.exit(1)

        # 5. Read Result and Output
        with open(temp_path, "rb") as f:
            output_data = f.read()

        # Write binary data to stdout buffer to avoid newline translation issues
        sys.stdout.buffer.write(output_data)
        sys.stdout.buffer.flush()

    finally:
        # 6. Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    main()
