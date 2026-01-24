#!/usr/bin/env python3

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="vydir - edit directories and filenames",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vydir               # Edit current directory
  vydir *.jpg         # Edit specific files
  find . | vydir -    # Edit pipe input
        """,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbosely display actions"
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], help="files, directories, or -"
    )
    args = parser.parse_args()

    files: list[str] = []
    read_stdin = False

    # 1. Collect Files
    for item in args.paths:
        if item == "-":
            if not read_stdin:
                try:
                    files.extend(line.rstrip("\n") for line in sys.stdin)
                except UnicodeDecodeError:
                    sys.stderr.write("vydir: Error reading non-UTF8 input from stdin\n")
                    sys.exit(1)
                read_stdin = True
        else:
            path = Path(item)
            if path.is_dir():
                try:
                    # non-recursive, sorted by name
                    contents = sorted(path.iterdir(), key=lambda p: p.name)
                    files.extend(str(p) for p in contents)
                except OSError as e:
                    sys.stderr.write(f"vydir: cannot read {item}: {e}\n")
                    sys.exit(1)
            else:
                files.append(item)

    if not files:
        sys.exit(0)

    # 2. Check Control Characters
    for f in files:
        if any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in f):
            sys.stderr.write(
                "vydir: control characters in filenames are not supported\n"
            )
            sys.exit(1)

    # 3. Create Temp File
    # Map ID -> Path. IDs start at 1.
    items = {i + 1: Path(f) for i, f in enumerate(files)}

    # Calculate zero-padding width
    width = len(str(len(files)))

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="vydir-",
        delete=False,
    )
    temp_path = Path(temp_file.name)

    try:
        with temp_file:
            for i in range(1, len(files) + 1):
                # Format: ID [TAB] Filename
                temp_file.write(f"{i:0{width}d}\t{items[i]}\n")

        # 4. Run Editor
        editor_cmd = os.getenv("EDITOR") or os.getenv("VISUAL") or "vi"
        editor_args = shlex.split(editor_cmd)
        editor_args.append(str(temp_path))

        # Explicitly open /dev/tty for the editor if possible
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
        except OSError:
            # Fallback if no TTY available
            if read_stdin:
                sys.stderr.write(
                    "vydir: Cannot launch interactive editor: input is piped and /dev/tty is unavailable.\n"
                )
                sys.exit(1)
            # Otherwise inherit stdio
            subprocess.run(editor_args, check=True)
        except subprocess.CalledProcessError:
            sys.stderr.write(f"vydir: {editor_cmd} exited nonzero, aborting\n")
            sys.exit(1)

        # 5. Read Result
        lines = temp_path.read_text(encoding="utf-8").splitlines()

    finally:
        if temp_path.exists():
            temp_path.unlink()

    # 6. Apply Changes
    line_re = re.compile(r"^(\d+)\s*\t?(.*)")
    error_occurred = False

    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue

        match = line_re.match(line)
        if not match:
            sys.stderr.write(f'vydir: unable to parse line "{line}", aborting\n')
            sys.exit(1)

        num = int(match.group(1))
        name = match.group(2)

        if num not in items:
            sys.stderr.write(f"vydir: unknown item number {num}\n")
            sys.exit(1)

        original_path = items[num]

        if name != str(original_path):
            if not name:
                # Empty name → treat as deletion (item remains in dict)
                continue

            src = original_path
            dest = Path(name)

            # Sanity check: does src exist?
            if not (src.exists() or src.is_symlink()):
                sys.stderr.write(f"vydir: {src} does not exist\n")
                del items[num]
                continue

            # Swap Handling: If dest exists, move it to dest~
            if dest.exists() or dest.is_symlink():
                backup = dest.with_name(dest.name + "~")
                c = 0
                while backup.exists() or backup.is_symlink():
                    c += 1
                    backup = dest.with_name(dest.name + f"~{c}")

                try:
                    dest.rename(backup)
                    if args.verbose:
                        print(f"'{dest}' -> '{backup}'")

                    # Update internal map
                    for k, v in items.items():
                        if v == dest:
                            items[k] = backup
                except OSError as e:
                    sys.stderr.write(f"vydir: failed to rename {dest} to {backup}: {e}\n")
                    error_occurred = True

            # Create parent directories if missing
            if dest.parent != Path(".") and not dest.parent.exists():
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    sys.stderr.write(
                        f"vydir: failed to create directory tree {dest.parent}: {e}\n"
                    )
                    error_occurred = True

            # Perform Rename
            try:
                src.rename(dest)
                if args.verbose:
                    print(f"'{src}' => '{dest}'")

                # Recursive Update Logic for directory renames
                if dest.is_dir():
                    for k, v in items.items():
                        if v == src:
                            continue
                        if v.is_relative_to(src):
                            rel = v.relative_to(src)
                            items[k] = dest / rel

            except OSError as e:
                sys.stderr.write(f"vydir: failed to rename {src} to {dest}: {e}\n")
                error_occurred = True

        # Remove processed item
        del items[num]

    # 7. Process Deletions
    # Remaining items were removed by the user → delete them.
    # Sort reverse alphabetically for depth-first deletion.
    to_delete = sorted(items.values(), key=str, reverse=True)

    for item in to_delete:
        try:
            if item.is_dir() and not item.is_symlink():
                item.rmdir()
            else:
                item.unlink()
            if args.verbose:
                print(f"removed '{item}'")
        except OSError as e:
            sys.stderr.write(f"vydir: failed to remove {item}: {e}\n")
            error_occurred = True

    sys.exit(1 if error_occurred else 0)


if __name__ == "__main__":
    main()