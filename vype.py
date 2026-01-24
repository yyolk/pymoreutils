#!/usr/bin/env python3

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="vype - edit stdin via $EDITOR and write the result to stdout",
        usage="%(prog)s [--suffix=extension]",
    )
    parser.add_argument(
        "--suffix",
        help="Optional file extension for the temporary file (e.g. '.csv', '.json') "
             "to enable syntax highlighting in the editor.",
    )
    args = parser.parse_args()

    suffix = args.suffix or ""
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"

    # Read all input (binary-safe)
    input_data = b""
    if not sys.stdin.isatty():
        try:
            input_data = sys.stdin.buffer.read()
        except Exception as e:
            sys.stderr.write(f"vype: error reading stdin: {e}\n")
            sys.exit(1)

    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(mode="w+b", suffix=suffix, delete=False)
    temp_path = Path(temp_file.name)

    try:
        with temp_file:
            temp_file.write(input_data)

        # Determine editor command
        editor_cmd = os.getenv("EDITOR") or os.getenv("VISUAL") or "vi"
        editor_args = shlex.split(editor_cmd)
        editor_args.append(str(temp_path))

        # Launch editor with explicit tty handling
        tty_path = Path("/dev/tty")
        try:
            with tty_path.open("r") as tty_in, tty_path.open("w") as tty_out:
                subprocess.run(
                    editor_args,
                    stdin=tty_in,
                    stdout=tty_out,
                    stderr=tty_out,
                    check=True,
                )
        except OSError as e:
            sys.stderr.write(
                f"vype: cannot open /dev/tty ({e}). Is this command running interactively?\n"
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            sys.stderr.write(
                f"vype: editor '{editor_cmd}' exited with status {e.returncode}\n"
            )
            sys.exit(1)

        # Output the edited content (binary-safe)
        output_data = temp_path.read_bytes()
        sys.stdout.buffer.write(output_data)
        sys.stdout.buffer.flush()

    finally:
        # Clean up the temporary file
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    main()