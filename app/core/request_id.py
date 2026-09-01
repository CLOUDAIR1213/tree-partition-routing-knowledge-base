import re
import secrets

from starlette.requests import Request

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def new_request_id() -> str:
    return f"req_{secrets.token_hex(12)}"


def request_id_from(request: Request) -> str:
    return request.state.request_id

