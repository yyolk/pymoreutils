#!/usr/bin/env python3
import sys
import shutil
import argparse
import tempfile
import textwrap
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="spunge - soak up standard input and write to a file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            description:
              Unlike a shell redirect (>), spunge reads all input before opening the output file.
              This allows reading from and writing to the same file in a pipeline.
        """),
    )
    parser.add_argument(
        "-a",
        "--append",
        action="store_true",
        help="Append to the file instead of overwriting.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="The file to write to. If omitted, writes to stdout.",
    )

    args = parser.parse_args()

    # 1. Soak up Input (Memory -> Disk spillover)
    max_memory = 10 * 1024 * 1024  # 10 MB

    with tempfile.SpooledTemporaryFile(max_size=max_memory, mode="w+b") as temp:
        # If appending, pre-load the original file content
        if args.append and args.file and args.file.exists():
            try:
                with args.file.open("rb") as f:
                    shutil.copyfileobj(f, temp)
            except OSError as e:
                sys.stderr.write(f"spunge: Error reading original file: {e}\n")
                sys.exit(1)

        # Append stdin
        try:
            shutil.copyfileobj(sys.stdin.buffer, temp)
        except Exception as e:
            sys.stderr.write(f"spunge: Error reading stdin: {e}\n")
            sys.exit(1)

        # 2. Output to stdout if no file argument
        if not args.file:
            temp.seek(0)
            shutil.copyfileobj(temp, sys.stdout.buffer)
            sys.exit(0)

        # 3. Atomic Write to File
        target_path = args.file
        target_dir = target_path.parent

        # Capture permissions from original file if it exists
        mode = None
        if target_path.exists():
            try:
                mode = target_path.stat().st_mode
            except OSError:
                pass

        try:
            # Create temp file in the same directory (required for atomic rename)
            with tempfile.NamedTemporaryFile(
                dir=target_dir, delete=False, prefix=".spunge_"
            ) as final_temp:
                temp.seek(0)
                shutil.copyfileobj(temp, final_temp)
                # Convert the string path from tempfile to a Path object
                temp_name = Path(final_temp.name)

            # Apply original permissions
            if mode is not None:
                temp_name.chmod(mode)

            # Atomic Rename (replaces os.replace)
            # This cleanly handles the "unlink old, link new" logic
            temp_name.replace(target_path)

        except OSError as e:
            sys.stderr.write(f"spunge: Error writing output: {e}\n")
            # Cleanup temp file on failure
            if "temp_name" in locals() and temp_name.exists():
                try:
                    # Replaces os.unlink
                    temp_name.unlink()
                except OSError:
                    pass
            sys.exit(1)


if __name__ == "__main__":
    main()
