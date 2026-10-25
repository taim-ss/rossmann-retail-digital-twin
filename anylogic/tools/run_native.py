"""Run the P2 model natively in AnyLogic PLE, one command-line run per (forecast source, seed).

Each run uses its own private copy of the generated model (AnyLogic needs folder name == model name) whose parameter
defaults are set for that run. A run counts only if its log contains the P2_DONE marker; a zero exit code is not proof.
Usage: python run_native.py --seeds 1-10 --sources 0,1,2 --label compare01 [--store 164]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_model  # noqa: E402
from native_runtime import launch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ANYLOGIC = Path("C:/Program Files/AnyLogic 8.9 Personal Learning Edition/AnyLogic.exe")


def parse_range(text: str) -> list[int]:
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in text.split(",")]


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--seeds", default="1-10")
    cli.add_argument("--sources", default="0,1,2")
    cli.add_argument("--label", required=True)
    cli.add_argument("--store", type=int, default=164)
    cli.add_argument("--data-dir", default=build_model.DATA.as_posix())
    cli.add_argument("--set", action="append", default=[], help="extra parameter override name=code, e.g. leadTimeDays=7.0")
    args = cli.parse_args()
    extra = dict(item.split("=", 1) for item in args.set)
    out = ROOT / "results" / "native" / args.label
    out.mkdir(parents=True, exist_ok=True)
    failures = []
    for src in parse_range(args.sources):
        for seed in parse_range(args.seeds):
            log = out / f"p2-store{args.store}-src{src}-seed{seed}.log"
            if log.exists():
                raise ValueError("Use a fresh --label; cached runs may have different data or parameters.")
            name = f"P2Run{args.label.replace('-', '').replace('_', '')}S{src}R{seed}"
            folder = ROOT / "tools" / ".build" / "runs" / name
            overrides = {"storeId": str(args.store), "forecastSource": str(src), "repSeed": str(seed), **extra}
            t0 = time.time()
            single_out = out / f"source{src}-seed{seed}"
            alp = build_model.build(name, folder, args.data_dir, single_out.as_posix(), overrides)
            launch(alp, "Simulation", single_out, 1)
            native_logs = list(single_out.glob("p2-store*.log"))
            ok = len(native_logs) == 1 and "P2_DONE" in native_logs[0].read_text(encoding="utf-8")
            if ok:
                log.write_text(native_logs[0].read_text(encoding="utf-8"), encoding="utf-8")
            print(f"src={src} seed={seed} ok={ok} {time.time() - t0:.0f}s", flush=True)
            if not ok:
                failures.append((src, seed))
    print("FAILED:", failures if failures else "none")


if __name__ == "__main__":
    main()
