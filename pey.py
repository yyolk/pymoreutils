#!/usr/bin/env python3
import sys
import subprocess
import argparse
import errno


def main():
    parser = argparse.ArgumentParser(
        description="pey - pipe standard input to multiple commands",
        epilog="Example: echo 'hello' | pey 'tr a-z A-Z' 'wc -c'",
    )
    # nargs='+' means we need at least one command
    parser.add_argument("commands", nargs="+", help="Commands to run")

    args = parser.parse_args()

    procs = []
    active_procs = []

    # 1. Start all subprocesses
    # We use shell=True to mimic popen(), allowing complex command strings.
    for cmd in args.commands:
        try:
            # bufsize=0: Unbuffered / binary mode
            p = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE)
            procs.append(p)
            active_procs.append(p)
        except OSError as e:
            sys.stderr.write(f"pey: Error starting '{cmd}': {e}\n")
            # If we fail to start one, should we abort?
            # The original usually tries to continue or exits based on severity.
            # We'll abort to be safe if a command is totally malformed.
            sys.exit(1)

    # 2. Multiplex Input
    try:
        while True:
            # Read chunk from stdin
            # 32KB is a reasonable buffer size for pipes
            chunk = sys.stdin.buffer.read(32768)

            if not chunk:
                break

            # Write chunk to all ACTIVE subprocesses
            # We iterate a copy of the list so we can remove dead ones safely
            for p in list(active_procs):
                try:
                    p.stdin.write(chunk)
                    p.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    # Handle broken pipe (e.g. 'head -n 1' finished early)
                    # errno 32 is Broken Pipe
                    if isinstance(e, BrokenPipeError) or e.errno == errno.EPIPE:
                        # Stop writing to this process, but close stdin properly
                        try:
                            p.stdin.close()
                        except:
                            pass
                        active_procs.remove(p)
                    else:
                        # Genuine I/O error, report it
                        sys.stderr.write(f"pey: Write error: {e}\n")
                        active_procs.remove(p)

    except KeyboardInterrupt:
        # Pass the interrupt to children implicitly via process group
        pass
    finally:
        # 3. Cleanup
        # Close stdin on all procs that are still expecting data
        for p in active_procs:
            try:
                p.stdin.close()
            except OSError:
                pass

        # 4. Gather Exit Codes
        # The exit code of pee is the OR of all exit codes.
        # (0 if all success, >0 if any failed)
        final_exit_code = 0

        for p in procs:
            try:
                ret = p.wait()
                # Accumulate errors (bitwise OR)
                final_exit_code |= ret
            except KeyboardInterrupt:
                pass

        sys.exit(final_exit_code)


if __name__ == "__main__":
    main()
