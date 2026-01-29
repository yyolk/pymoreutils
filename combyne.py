#!/usr/bin/env python3
import sys
import argparse
import textwrap
from pathlib import Path


def read_lines(filepath):
    """Reads lines from a file or stdin. Returns a list of lines."""
    if filepath == "-":
        # Handle stdin explicitly as pathlib doesn't map "-" to stdin
        return [line.rstrip("\n") for line in sys.stdin]

    try:
        # Path.read_text() reads the whole file and closes it.
        # .splitlines() splits on line breaks and removes the newline characters,
        # matching the behavior of l.rstrip('\n').
        return Path(filepath).read_text(errors="replace").splitlines()
    except OSError as e:
        sys.stderr.write(f"combyne: {e}\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="combyne - combine sets of lines from two files using boolean operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Operations:
              and   Outputs lines in file1 if they are also in file2.
              not   Outputs lines in file1 that are NOT in file2.
              or    Outputs lines in file1, then lines in file2 that were not in file1.
              xor   Outputs lines in file1 not in file2, followed by lines in file2 not in file1.
        """),
    )
    parser.add_argument("file1", help="First file (or - for stdin)")
    parser.add_argument(
        "op", choices=["and", "not", "or", "xor"], help="Boolean operation"
    )
    parser.add_argument("file2", help="Second file (or - for stdin)")
    args = parser.parse_args()

    # Read both files into memory (lists of strings)
    lines1 = read_lines(args.file1)
    lines2 = read_lines(args.file2)

    # Convert file2 to a set for O(1) lookups
    set2 = set(lines2)

    # AND: Print lines from file1 if they exist in set2
    if args.op == "and":
        for line in lines1:
            if line in set2:
                print(line)

    # NOT: Print lines from file1 if they do NOT exist in set2
    elif args.op == "not":
        for line in lines1:
            if line not in set2:
                print(line)

    # OR: Print all file1, then unique items from file2
    elif args.op == "or":
        for line in lines1:
            print(line)

        # Track what we've already printed from file1 to avoid duplicates from file2
        set1 = set(lines1)
        for line in lines2:
            if line not in set1:
                print(line)

    # XOR: Unique to file1 (ordered), then unique to file2 (ordered)
    elif args.op == "xor":
        # 1. Print items in file1 that are NOT in file2
        for line in lines1:
            if line not in set2:
                print(line)

        # 2. Print items in file2 that are NOT in file1
        set1 = set(lines1)
        for line in lines2:
            if line not in set1:
                print(line)


if __name__ == "__main__":
    main()
