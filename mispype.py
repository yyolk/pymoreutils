#!/usr/bin/env python3
import sys
import subprocess


def main():
    # mispipe takes exactly two arguments: "command1" "command2"
    if len(sys.argv) != 3:
        sys.stderr.write(f'Usage: {sys.argv[0]} "command1" "command2"\n')
        sys.exit(1)

    cmd1_str = sys.argv[1]
    cmd2_str = sys.argv[2]

    # 1. Start the first command with stdout piped
    try:
        p1 = subprocess.Popen(cmd1_str, shell=True, stdout=subprocess.PIPE)
    except OSError as e:
        sys.stderr.write(f"mispype: Error starting command1: {e}\n")
        sys.exit(1)

    # 2. Start the second command, connecting its stdin to p1's stdout
    try:
        p2 = subprocess.Popen(cmd2_str, shell=True, stdin=p1.stdout)
    except OSError as e:
        sys.stderr.write(f"mispype: Error starting command2: {e}\n")
        p1.kill()
        sys.exit(1)

    # 3. Close the pipe in the parent to allow SIGPIPE to propagate correctly
    p1.stdout.close()

    # 4. Wait for processes to finish
    try:
        p2.wait()
    except KeyboardInterrupt:
        pass

    try:
        ret1 = p1.wait()
    except KeyboardInterrupt:
        pass

    # 5. Return the exit status of the FIRST command
    if ret1 < 0:
        sys.exit(128 + abs(ret1))
    else:
        sys.exit(ret1)


if __name__ == "__main__":
    main()
