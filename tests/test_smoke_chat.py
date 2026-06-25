import io

import httpx

from scripts.smoke_chat import print_line, request_with_retries


def test_print_line_handles_chinese_on_cp950_stream():
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp950", errors="strict")

    print_line("chat 200: 根据检索到的资料", stream=stream)
    stream.flush()

    assert b"chat 200:" in buffer.getvalue()


def test_request_with_retries_handles_initial_connect_error():
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("not ready")
        return "ok"

    assert request_with_retries(operation, attempts=2, delay=0) == "ok"
    assert attempts["count"] == 2
