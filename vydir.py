#!/usr/bin/env python3
import sys
import os
import argparse
import tempfile
import subprocess
import shlex
import re


def main():
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

    files = []
    read_stdin = False

    # 1. Collect Files
    for item in args.paths:
        if item == "-":
            if not read_stdin:
                # Read from stdin
                try:
                    files.extend(line.rstrip("\n") for line in sys.stdin)
                except UnicodeDecodeError:
                    sys.stderr.write("vydir: Error reading non-UTF8 input from stdin\n")
                    sys.exit(1)
                read_stdin = True
        elif os.path.isdir(item):
            # Strip trailing slash for consistency
            clean_item = item.rstrip(os.sep)
            if not clean_item:
                clean_item = os.sep
            try:
                # non-recursive list, sorted
                contents = sorted(os.listdir(clean_item))
                files.extend(os.path.join(clean_item, f) for f in contents)
            except OSError as e:
                sys.stderr.write(f"vydir: cannot read {item}: {e}\n")
                sys.exit(1)
        else:
            files.append(item)

    if not files:
        sys.exit(0)

    # 2. Check Control Characters
    # Perl's [[:cntrl:]] includes 0-31 and 127.
    for f in files:
        if any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in f):
            sys.stderr.write(
                "vydir: control characters in filenames are not supported\n"
            )
            sys.exit(1)

    # 3. Create Temp File
    # Map ID -> Filename. IDs start at 1.
    # We use a dict to track the *current* location of files (handled files are removed)
    items = {i + 1: f for i, f in enumerate(files)}

    # Calculate zero-padding width
    width = len(str(len(files)))

    tf_fd, tf_path = tempfile.mkstemp(prefix="dir", text=True)
    try:
        with os.fdopen(tf_fd, "w") as tf:
            for i in range(1, len(files) + 1):
                # Format: ID [TAB] Filename
                tf.write(f"{i:0{width}d}\t{items[i]}\n")

        # 4. Run Editor
        editor_cmd = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
        editor_args = shlex.split(editor_cmd)
        editor_args.append(tf_path)

        # We must explicitly open /dev/tty for the editor if our stdin is a pipe
        try:
            with open("/dev/tty", "r") as tty_in, open("/dev/tty", "w") as tty_out:
                subprocess.check_call(
                    editor_args, stdin=tty_in, stdout=tty_out, stderr=tty_out
                )
        except OSError:
            # Fallback if no TTY available (e.g. running in cron or non-interactive shell)
            # If we read from stdin (-), we can't reuse sys.stdin.
            if read_stdin:
                sys.stderr.write(
                    "vydir: Cannot launch interactive editor: input is piped and /dev/tty is unavailable.\n"
                )
                sys.exit(1)
            # Otherwise try standard inheritance
            subprocess.check_call(editor_args)
        except subprocess.CalledProcessError:
            sys.stderr.write(f"vydir: {editor_cmd} exited nonzero, aborting\n")
            sys.exit(1)

        # 5. Read Result
        with open(tf_path, "r") as tf:
            lines = tf.readlines()

    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)

    # 6. Apply Changes
    # Regex to parse lines: integer ID, optional tab/space, filename
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

        original_name = items[num]

        # If the name has changed (and isn't empty)
        if name != original_name:
            if not name:
                # If name is cleared but ID remains, treat as ignore (or delete?)
                # vidir keeps the item in the dict, which means it falls through to the deletion loop below.
                continue

            src = original_name
            dest = name

            # Sanity check: does src exist?
            if not (os.path.exists(src) or os.path.islink(src)):
                sys.stderr.write(f"vydir: {src} does not exist\n")
                del items[num]
                continue

            # Swap Handling: If dest exists, move it to dest~
            if os.path.exists(dest) or os.path.islink(dest):
                tmp = dest + "~"
                c = 0
                while os.path.exists(tmp) or os.path.islink(tmp):
                    c += 1
                    tmp = f"{dest}~{c}"

                try:
                    os.rename(dest, tmp)
                    if args.verbose:
                        print(f"'{dest}' -> '{tmp}'")

                    # Update internal map: whatever ID pointed to 'dest' now points to 'tmp'
                    # This ensures we don't try to rename 'dest' later thinking it's still there.
                    for k, v in items.items():
                        if v == dest:
                            items[k] = tmp
                except OSError as e:
                    sys.stderr.write(f"vydir: failed to rename {dest} to {tmp}: {e}\n")
                    error_occurred = True

            # Create parent directories if missing
            dest_dir = os.path.dirname(dest)
            if dest_dir and not os.path.exists(dest_dir):
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                except OSError as e:
                    sys.stderr.write(
                        f"vydir: failed to create directory tree {dest_dir}: {e}\n"
                    )
                    error_occurred = True

            # Perform Rename
            try:
                os.rename(src, dest)
                if args.verbose:
                    print(f"'{src}' => '{dest}'")

                # Recursive Update Logic:
                # If we renamed a directory, we must update the paths of any files
                # inside it that are still waiting in the 'items' dict.
                if os.path.isdir(dest):
                    src_slash = src + os.sep
                    len_src = len(src)
                    for k, v in items.items():
                        if v == src:
                            continue
                        if v.startswith(src_slash):
                            suffix = v[len_src:]  # e.g. "/subdir/file"
                            items[k] = dest + suffix

            except OSError as e:
                sys.stderr.write(f"vydir: failed to rename {src} to {dest}: {e}\n")
                error_occurred = True

        # Remove processed item from dict
        del items[num]

    # 7. Process Deletions
    # Any item remaining in 'items' was removed from the text file by the user.
    # We sort reverse alphabetically. This acts as a depth-first sort
    # (e.g., "a/b" comes before "a" in reverse), ensuring children are deleted before parents.
    to_delete = sorted(items.values(), reverse=True)

    for item in to_delete:
        try:
            # Use rmdir for directories (safety: only works if empty), remove for files
            if os.path.isdir(item) and not os.path.islink(item):
                os.rmdir(item)
            else:
                os.remove(item)
            if args.verbose:
                print(f"removed '{item}'")
        except OSError as e:
            sys.stderr.write(f"vydir: failed to remove {item}: {e}\n")
            error_occurred = True

    sys.exit(1 if error_occurred else 0)


if __name__ == "__main__":
    main()
