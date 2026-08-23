"""带 Range 支持的静态服务器。

标准库的 SimpleHTTPRequestHandler **不支持 Range**，浏览器无法 seek，
video.currentTime = X 之后 seeked 事件永远不来。另外它是单线程的，
视频流会占住唯一的连接。两个问题都要解决。

这正是 SPEC §5.3 对 /api/media/{id}/stream 的同一条硬要求。
"""

from __future__ import annotations

import os
import re
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class _Limited:
    """只允许读出 n 字节的文件包装，用于截断 206 响应体。"""

    def __init__(self, f, n):
        self.f, self.left = f, n

    def read(self, amt=-1):
        if self.left <= 0:
            return b""
        amt = self.left if amt < 0 else min(amt, self.left)
        data = self.f.read(amt)
        self.left -= len(data)
        return data

    def close(self):
        self.f.close()


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None

        size = os.fstat(f.fileno()).st_size
        m = _RANGE.match(rng.strip())
        if not m:
            f.close()
            self.send_error(HTTPStatus.BAD_REQUEST)
            return None

        first, last = m.group(1), m.group(2)
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        else:
            start = max(0, size - int(last or 0))
            end = size - 1
        end = min(end, size - 1)

        if start >= size or start > end:
            f.close()
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        f.seek(start)
        return _Limited(f, end - start + 1)

    def send_response(self, code, message=None):
        super().send_response(code, message)
        if code == HTTPStatus.OK:
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    srv = ThreadingHTTPServer(("127.0.0.1", 8099), partial(RangeHandler, directory=here))
    print("serving %s on http://127.0.0.1:8099" % here, flush=True)
    srv.serve_forever()
