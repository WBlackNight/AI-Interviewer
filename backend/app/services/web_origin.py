"""WebSocket origin checks for explicit cross-origin and same-origin deployments."""
from urllib.parse import urlsplit


def allowed_origin(websocket, allowed):
    origin = websocket.headers.get('origin')
    if not origin:
        return False
    if origin in allowed:
        return True
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    expected_scheme = 'https' if websocket.scope.get('scheme') == 'wss' else 'http'
    return (parsed.scheme == expected_scheme and bool(parsed.netloc)
            and not parsed.username and not parsed.password and not parsed.path
            and not parsed.query and not parsed.fragment
            and parsed.netloc.lower() == websocket.headers.get('host', '').lower())
