"""
Data Integrity Verification — zone_prep source chain of custody.

Reads zone_prep_manifest.json and verifies SHA256 hashes of all
source files and merged outputs. Reports MATCH or MISMATCH.

Usage:
    python scripts/verify_data_integrity.py
    make verify-data

Exit codes:
    0 = all hashes match
    1 = at least one mismatch or missing file
"""
import hashlib, json, sys, os

MANIFEST_PATH = 'stages/01-data/output/zone_prep/zone_prep_manifest.json'

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def count_rows(path):
    with open(path, 'r') as f:
        return sum(1 for _ in f) - 1

def verify_group(label, entries, base_dir):
    ok = 0
    fail = 0
    missing = 0

    for key, info in entries.items():
        path = info.get('path', '')
        if not path:
            path = os.path.join(
                'stages/01-data/output/zone_prep', info['file'])
        full_path = os.path.join(base_dir, path)

        if not os.path.exists(full_path):
            print(f"  MISSING  {key}: {path}")
            missing += 1
            continue

        actual_hash = sha256_file(full_path)
        expected_hash = info['sha256']
        actual_rows = count_rows(full_path)
        expected_rows = info['rows']

        if actual_hash == expected_hash and actual_rows == expected_rows:
            print(f"  MATCH    {key}: {info['file']} ({actual_rows} rows)")
            ok += 1
        else:
            fail += 1
            if actual_hash != expected_hash:
                print(f"  MISMATCH {key}: {info['file']} hash differs")
                print(f"           expected: {expected_hash[:16]}...")
                print(f"           actual:   {actual_hash[:16]}...")
            if actual_rows != expected_rows:
                print(f"  MISMATCH {key}: {info['file']} rows "
                      f"{expected_rows} -> {actual_rows}")

    return ok, fail, missing

def main():
    # Find project root (directory containing stages/)
    base_dir = os.getcwd()
    manifest_full = os.path.join(base_dir, MANIFEST_PATH)
    if not os.path.exists(manifest_full):
        # Try one level up
        base_dir = os.path.dirname(base_dir)
        manifest_full = os.path.join(base_dir, MANIFEST_PATH)
    if not os.path.exists(manifest_full):
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        sys.exit(1)

    with open(manifest_full) as f:
        manifest = json.load(f)

    print(f"Data Integrity Verification")
    print(f"Manifest generated: {manifest['generated_at']}")
    print(f"Last verified:      {manifest.get('verified_at', 'never')}")
    print()

    total_ok = total_fail = total_missing = 0

    print("Source files:")
    ok, fail, missing = verify_group(
        "source", manifest['source_files'], base_dir)
    total_ok += ok; total_fail += fail; total_missing += missing

    print("\nMerged outputs:")
    ok, fail, missing = verify_group(
        "merged", manifest['merged_outputs'], base_dir)
    total_ok += ok; total_fail += fail; total_missing += missing

    # Population check
    print(f"\nQualifying touches (P2): {manifest.get('qualifying_touches_p2', '?')}")

    print(f"\n{'='*50}")
    if total_fail == 0 and total_missing == 0:
        print(f"PASS: {total_ok}/{total_ok} files verified")
        sys.exit(0)
    else:
        print(f"FAIL: {total_fail} mismatched, {total_missing} missing "
              f"({total_ok} ok)")
        sys.exit(1)

if __name__ == '__main__':
    main()
