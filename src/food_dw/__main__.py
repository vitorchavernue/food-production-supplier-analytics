"""Command line of the project.

python -m food_dw deploy    # create the warehouse (PostgreSQL)
python -m food_dw erp       # create the ERP tables on Oracle with 21 months of history
python -m food_dw run       # run the Hop workflow once
python -m food_dw export    # write the CSV files for Qlik (only after a passed run)
python -m food_dw demo      # everything: full load, export, one more ERP day, incremental load, rerun
"""

from __future__ import annotations

import sys

from food_dw import deploy, export, oracle_load, run


def demo() -> int:
    deploy.deploy()
    data, state = oracle_load.load_history()
    first = run.run_job("first_load")
    print(run.report(first, "First load (01/2025 - 09/2026)"))
    hashes = export.export_all()
    if "--write-manifest" in sys.argv:
        export.write_manifest(hashes)
    diff = export.differences(hashes)
    print(f"Exported files identical to the committed ones: {'yes' if not diff else 'NO: ' + ', '.join(diff)}")

    oracle_load.load_next_day(data, state)
    second = run.run_job("incremental")
    print(run.report(second, "Incremental load (one more day + corrections)"))
    third = run.run_job("rerun")
    print(run.report(third, "Rerun without ERP changes"))
    ok = first.passed and second.passed and third.passed and not diff
    return 0 if ok else 1


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if command == "deploy":
        deploy.deploy()
    elif command == "erp":
        oracle_load.load_history()
    elif command == "run":
        print(run.report(run.run_job("manual"), "Manual run"))
    elif command == "export":
        hashes = export.export_all()
        if "--write-manifest" in sys.argv:
            export.write_manifest(hashes)
        print(f"{len(hashes)} files written to {export.OUT}")
    elif command == "demo":
        return demo()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
