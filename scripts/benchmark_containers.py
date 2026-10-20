"""Compare live Python containers with explicit JS snapshots, including copy cost.

Run after installation: python scripts/benchmark_containers.py
Each size runs in a fresh process. Modes are warmed up and sampled in shuffled
order, with matching checksums. Timings include evaluate() overhead and are local
measurements, not performance guarantees. SDK logs are hidden on successful runs.
"""

import argparse
import json
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

from ultralight_py import Runtime


def sample(view, cases, iterations, warmup):
    samples = {name: [] for name in cases}
    rng = random.Random(1)
    for repeat in range(warmup + iterations):
        names = list(cases)
        rng.shuffle(names)
        for name in names:
            source, expected = cases[name]
            start = time.perf_counter_ns()
            actual = view.evaluate(source)
            elapsed = (time.perf_counter_ns() - start) / 1e6
            if actual != expected:
                raise AssertionError((name, actual, expected))
            if repeat >= warmup:
                samples[name].append(elapsed)
    return {
        name: {
            "median_ms": round(statistics.median(values), 6),
            "min_ms": round(min(values), 6),
            "max_ms": round(max(values), 6),
        }
        for name, values in samples.items()
    }


def worker(args):
    size = args.sizes[0]
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        ready, failed = [], []
        view.set_callbacks(
            dom_ready=lambda event: ready.append(event) if event.is_main_frame else None,
            fail_loading=failed.append,
        )
        view.load_html("<body>")
        deadline = time.monotonic() + 10
        while not ready and not failed and time.monotonic() < deadline:
            runtime.update()
        if not ready or failed:
            raise RuntimeError(f"Benchmark page failed to load: {failed}")
        inputs = {
            "items": list(range(size)),
            "mapping": {"value": 7, **{f"k{i}": i for i in range(size)}},
            "nested": [{"value": i} for i in range(size)],
        }
        for name, value in inputs.items():
            view.bind_object(name, value)
            view.evaluate(f"globalThis.{name}Copy=Python.to_value({name}); void 0")
        view.evaluate("globalThis.benchmarkSize=" + str(size))
        view.evaluate("""
          globalThis.readIndex=(a,n)=>{let s=0;for(let i=0;i<n;i++)s+=a[i%benchmarkSize];return s;};
          globalThis.readField=(a,n)=>{let s=0;for(let i=0;i<n;i++)s+=a.value;return s;};
          globalThis.readNested=(a,n)=>{let s=0;for(let i=0;i<n;i++)s+=a[i%benchmarkSize].value;return s;};
          globalThis.readLength=(a,n)=>{let s=0;for(let i=0;i<n;i++)s+=a.length;return s;};
          globalThis.readMap=a=>a.map(x=>x+1).reduce((a,b)=>a+b,0);void 0;
        """)
        copies = sample(
            view,
            {name: (f"(Python.to_value({name}),null)", None) for name in inputs},
            args.iterations,
            args.warmup,
        )
        print(json.dumps({"size": size, "copy_only": copies}))
        for reads in args.reads:
            cycles, tail = divmod(reads, size)
            total = cycles * size * (size - 1) // 2 + tail * (tail - 1) // 2
            workloads = [
                ("list_index", "readIndex", "items", total),
                ("dict_field", "readField", "mapping", reads * 7),
                ("nested_field", "readNested", "nested", total),
                ("list_length", "readLength", "items", reads * size),
            ]
            for label, function, name, expected in workloads:
                modes = {
                    "live": (f"{function}({name},{reads})", expected),
                    "pre_copied": (f"{function}({name}Copy,{reads})", expected),
                    "copy_and_read": (f"{function}(Python.to_value({name}),{reads})", expected),
                }
                result = sample(view, modes, args.iterations, args.warmup)
                print(json.dumps({"size": size, "reads": reads, "case": label, **result}))
        result = sample(
            view,
            {
                mode: (f"readMap({source})", size * (size + 1) // 2)
                for mode, source in {
                    "live": "items",
                    "pre_copied": "itemsCopy",
                    "copy_and_read": "Python.to_value(items)",
                }.items()
            },
            args.iterations,
            args.warmup,
        )
        print(json.dumps({"size": size, "reads": size, "case": "map_reduce", **result}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[16, 1024])
    parser.add_argument("--reads", type=int, nargs="+", default=[1, 10, 100, 1000, 10000])
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.sizes + args.reads + [args.iterations]) < 1 or args.warmup < 0:
        parser.error("sizes, reads and iterations must be positive; warmup must be nonnegative")
    if args.worker:
        worker(args)
        return
    print(json.dumps({"python": sys.version, "platform": platform.platform(), **vars(args)}))
    for size in args.sizes:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--sizes",
                str(size),
                "--reads",
                *map(str, args.reads),
                "--iterations",
                str(args.iterations),
                "--warmup",
                str(args.warmup),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        for line in result.stdout.splitlines():
            if line.startswith("{"):
                print(line)


if __name__ == "__main__":
    main()
