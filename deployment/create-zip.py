#!/usr/bin/env python3
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def create_zip(source_dir: Path, output_file: Path, max_uncompressed_mib: int | None) -> None:
    source_dir = source_dir.resolve()
    output_file = output_file.resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    source_files = [file_path for file_path in sorted(source_dir.rglob("*")) if file_path.is_file()]
    uncompressed_size = sum(file_path.stat().st_size for file_path in source_files)

    if max_uncompressed_mib is not None:
        max_uncompressed_bytes = max_uncompressed_mib * 1024 * 1024
        if uncompressed_size > max_uncompressed_bytes:
            raise ValueError(
                f"Uncompressed package is {uncompressed_size / 1024 / 1024:.1f} MiB; "
                f"limit is {max_uncompressed_mib} MiB."
            )

    with ZipFile(output_file, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for file_path in source_files:
            relative_path = file_path.relative_to(source_dir).as_posix()
            info = ZipInfo(relative_path, date_time=FIXED_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (file_path.stat().st_mode & 0xFFFF) << 16
            with file_path.open("rb") as source:
                archive.writestr(info, source.read())

    print(
        f"Created {output_file} "
        f"({output_file.stat().st_size / 1024 / 1024:.1f} MiB compressed, "
        f"{uncompressed_size / 1024 / 1024:.1f} MiB uncompressed)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic ZIP archive.")
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--max-uncompressed-mib", type=int)
    args = parser.parse_args()

    if not args.source_dir.is_dir():
        parser.error(f"Source directory does not exist: {args.source_dir}")

    create_zip(args.source_dir, args.output_file, args.max_uncompressed_mib)


if __name__ == "__main__":
    main()
