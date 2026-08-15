from __future__ import annotations

import os
import time

__all__ = [
    "ScannerBudgetError",
    "MAX_FILE_BYTES",
    "MAX_TOTAL_BYTES",
    "MAX_FILE_COUNT",
    "MAX_WALK_DEPTH",
    "MAX_SCAN_SECONDS",
    "MAX_JSON_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_NESTING_DEPTH",
    "MAX_WORKSPACE_MATCHES",
    "read_text_limited",
    "json_bytes_guard",
    "json_nesting_depth",
    "check_json_depth",
    "WalkBudget",
]

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILE_COUNT = 20000
MAX_WALK_DEPTH = 100
MAX_SCAN_SECONDS = 60.0
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_JSON_DEPTH = 512
MAX_NESTING_DEPTH = 256
MAX_WORKSPACE_MATCHES = 1000


class ScannerBudgetError(Exception):
    def __init__(self, budget_name: str, limit):
        self.budget_name = budget_name
        self.limit = limit
        super().__init__(f"scan budget exceeded: {budget_name} ({limit})")


def read_text_limited(path, max_bytes=MAX_FILE_BYTES) -> str:
    if max_bytes is None:
        max_bytes = MAX_FILE_BYTES
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        data = file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ScannerBudgetError("file_bytes", max_bytes)
    return data


def json_bytes_guard(path, max_bytes=MAX_JSON_BYTES):
    if max_bytes is None:
        max_bytes = MAX_JSON_BYTES
    if os.path.getsize(path) > max_bytes:
        raise ScannerBudgetError("json_bytes", max_bytes)


def json_nesting_depth(text) -> int:
    depth = 0
    max_depth = 0
    quote: str | None = None
    escaped = False
    for character in text:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "\"'":
            quote = character
            continue
        if character in "{[":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif character in "}]":
            if depth > 0:
                depth -= 1
    return max_depth


def check_json_depth(text, max_depth=MAX_JSON_DEPTH):
    if max_depth is None:
        max_depth = MAX_JSON_DEPTH
    if json_nesting_depth(text) > max_depth:
        raise ScannerBudgetError("json_depth", max_depth)


class WalkBudget:
    def __init__(
        self,
        repo_root,
        *,
        max_bytes=MAX_TOTAL_BYTES,
        max_files=MAX_FILE_COUNT,
        max_depth=MAX_WALK_DEPTH,
        max_seconds=MAX_SCAN_SECONDS,
    ):
        self.repo_root = repo_root
        if max_bytes is None:
            max_bytes = MAX_TOTAL_BYTES
        if max_files is None:
            max_files = MAX_FILE_COUNT
        if max_depth is None:
            max_depth = MAX_WALK_DEPTH
        if max_seconds is None:
            max_seconds = MAX_SCAN_SECONDS
        self.max_bytes = max_bytes
        self.max_files = max_files
        self.max_depth = max_depth
        self.max_seconds = max_seconds
        self.start = time.monotonic()
        self.bytes_processed = 0
        self.files_processed = 0
        self.dir_depth = 0

    def touch_bytes(self, n):
        self.bytes_processed += n
        self.check()

    def touch_file(self, path, size=None):
        self.files_processed += 1
        if size is None:
            size = os.path.getsize(path)
        self.bytes_processed += size
        self.check()

    def enter_dir(self):
        self.dir_depth += 1
        if self.dir_depth > self.max_depth:
            self.dir_depth -= 1
            raise ScannerBudgetError("depth", self.max_depth)
        self.check()

    def exit_dir(self):
        if self.dir_depth > 0:
            self.dir_depth -= 1

    def check(self):
        if self.bytes_processed > self.max_bytes:
            raise ScannerBudgetError("bytes", self.max_bytes)
        if self.files_processed > self.max_files:
            raise ScannerBudgetError("files", self.max_files)
        if self.dir_depth > self.max_depth:
            raise ScannerBudgetError("depth", self.max_depth)
        if time.monotonic() - self.start >= self.max_seconds:
            raise ScannerBudgetError("seconds", self.max_seconds)
