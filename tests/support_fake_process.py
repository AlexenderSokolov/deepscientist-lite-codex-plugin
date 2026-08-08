from __future__ import annotations

import json
import queue


class _Input:
    def __init__(self, process):
        self.process = process

    def write(self, value):
        message = json.loads(value)
        self.process.writes.append(message)
        self.process.on_write(message)

    def flush(self):
        return None


class _Output:
    def __init__(self, process):
        self.process = process

    def readline(self):
        return self.process.lines.get(timeout=5)


class FakeProcess:
    def __init__(self, on_write):
        self.lines = queue.Queue()
        self.writes = []
        self.on_write = on_write
        self.stdin = _Input(self)
        self.stdout = _Output(self)

    def emit(self, message):
        self.lines.put(json.dumps(message) + "\n")

    def close(self):
        self.lines.put("")
