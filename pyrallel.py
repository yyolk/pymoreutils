#!/usr/bin/env python3
import sys
import os
import time
import subprocess
import argparse


def main():
    # We must handle the double-dash '--' separator manually because argparse
    # doesn't easily distinguish between command arguments and parallel's own flags.
    if "--" not in sys.argv:
        sys.stderr.write("Usage: pyrallel [OPTIONS] command -- arguments\n")
        sys.stderr.write("       pyrallel [OPTIONS] -- commands\n")
        sys.exit(1)

    dash_idx = sys.argv.index("--")
    pre_dash = sys.argv[1:dash_idx]
    arguments = sys.argv[dash_idx + 1 :]

    parser = argparse.ArgumentParser(
        description="pyrallel - run programs in parallel", add_help=False
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="Show this help message"
    )
    parser.add_argument(
        "-j",
        type=int,
        default=os.cpu_count() or 1,
        help="Limit the number of jobs run at the same time (default: CPU count).",
    )
    parser.add_argument(
        "-l",
        type=float,
        default=-1.0,
        help="Wait to start new jobs if load average is above this limit.",
    )
    parser.add_argument(
        "-i", action="store_true", help="Replace '{}' in the command with the argument."
    )
    parser.add_argument(
        "-n",
        type=int,
        default=1,
        help="Number of arguments to pass to a command at a time. Default 1.",
    )

    # parse_known_args separates pyrallel's flags from the actual command it needs to run
    args, command = parser.parse_known_args(pre_dash)

    if args.help:
        print("Usage: pyrallel [OPTIONS] command -- arguments")
        print("       pyrallel [OPTIONS] -- commands")
        parser.print_help()
        sys.exit(0)

    if args.i and args.n > 1:
        sys.stderr.write("pyrallel: options -i and -n are incompatible\n")
        sys.exit(2)

    if args.n > 1 and not command:
        sys.stderr.write("pyrallel: option -n cannot be used without a command\n")
        sys.exit(2)

    maxjobs = args.j
    maxload = args.l
    argsatonce = args.n
    replace_cb = args.i

    active_procs = []
    final_exit_code = 0
    argidx = 0

    def wait_for_job(block=True):
        """Polls running processes. Removes finished ones and records their exit code."""
        nonlocal final_exit_code
        while active_procs:
            for p in active_procs:
                ret = p.poll()
                if ret is not None:
                    active_procs.remove(p)
                    # Exit status is the bitwise OR of all child exit statuses
                    final_exit_code |= abs(ret)
                    return True

            if block:
                # Sleep briefly to prevent pinning the CPU while waiting
                time.sleep(0.05)
            else:
                return False
        return False

    def get_load_average():
        """Cross-platform safe load average check."""
        try:
            return os.getloadavg()[0]  # 1-minute load average
        except AttributeError:
            return 0.0  # Fallback for Windows where getloadavg doesn't exist

    # Main Job Control Loop
    while argidx < len(arguments):
        # 1. Check System Load
        if maxload > 0 and get_load_average() >= maxload:
            wait_for_job(block=True)
            continue

        # 2. Check Concurrent Job Limit
        if maxjobs > 0 and len(active_procs) >= maxjobs:
            wait_for_job(block=True)
            continue

        # 3. We are clear to start a new job
        batch_size = min(argsatonce, len(arguments) - argidx)
        batch_args = arguments[argidx : argidx + batch_size]
        argidx += batch_size

        if command:
            # Usage 1: Run 'command' with 'arguments'
            cmd = []
            for part in command:
                if replace_cb and "{}" in part:
                    cmd.append(part.replace("{}", batch_args[0]))
                else:
                    cmd.append(part)

            if not replace_cb:
                cmd.extend(batch_args)

            try:
                # Spawn process, inheriting stdin/stdout/stderr
                p = subprocess.Popen(cmd)
                active_procs.append(p)
            except OSError as e:
                sys.stderr.write(f"pyrallel: error executing '{cmd[0]}': {e}\n")
                final_exit_code |= 1
        else:
            # Usage 2: Treat each argument as a standalone shell command
            cmd_str = batch_args[0]
            try:
                p = subprocess.Popen(cmd_str, shell=True)
                active_procs.append(p)
            except OSError as e:
                sys.stderr.write(f"pyrallel: error executing '{cmd_str}': {e}\n")
                final_exit_code |= 1

    # Drain any remaining active jobs before exiting
    while active_procs:
        wait_for_job(block=True)

    sys.exit(final_exit_code)


if __name__ == "__main__":
    main()
