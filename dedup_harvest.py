#!/usr/bin/env python3
"""Deduplicate the three harvest files: facts.jsonl, corrections.jsonl, avoid.jsonl"""

import json
import sys
from pathlib import Path

def dedup_file(filepath, key_field):
    """Remove duplicate entries from a JSONL file based on the value of key_field."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return

    seen = set()
    unique_entries = []
    duplicates = []

    with open(path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                value = entry.get(key_field, '')
                if value in seen:
                    duplicates.append((line_num, value))
                else:
                    seen.add(value)
                    unique_entries.append(entry)
            except json.JSONDecodeError as e:
                print(f"Warning: skipping malformed line {line_num} in {filepath}: {e}")

    # Write back unique entries
    with open(path, 'w') as f:
        for entry in unique_entries:
            f.write(json.dumps(entry) + '\n')

    print(f"  {filepath}: {len(unique_entries)} unique, {len(duplicates)} duplicates removed")
    for ln, val in duplicates:
        print(f"    Line {ln}: {val[:80]}...")

    return len(unique_entries), len(duplicates)

if __name__ == '__main__':
    files = [
        ('/opt/data/level_up/harvest/facts.jsonl', 'fact'),
        ('/opt/data/level_up/harvest/corrections.jsonl', 'correction'),
        ('/opt/data/level_up/harvest/avoid.jsonl', 'avoid'),
    ]

    for filepath, key_field in files:
        print(f"Deduplicating {filepath}...")
        dedup_file(filepath, key_field)
