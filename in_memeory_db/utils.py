import socket
import time
import json


def fast_http_request(method, path, body=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 8080))

    if body:
        body_str = body
        request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body_str)}\r\n\r\n{body_str}"
    else:
        request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n\r\n"

    sock.send(request.encode())
    response = sock.recv(4096).decode()
    sock.close()

    return response


def get_body_from_response(response):
    return json.loads(response.split("\r\n\r\n", 1)[1])


def add_item(item):
    body = f'{{"item":"{item}"}}'
    response = fast_http_request("POST", "/add", body)
    return response


def clear_items():
    response = fast_http_request("POST", "/clear")
    return response


def contains_item(item):
    body = f'{{"item":"{item}"}}'
    response = fast_http_request("POST", "/contains", body)
    body = get_body_from_response(response)
    return body["exists"]


def size():
    response = fast_http_request("GET", "/size")
    body = get_body_from_response(response)
    return int(body["size"])
