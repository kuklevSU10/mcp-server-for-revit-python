# -*- coding: utf-8 -*-
"""
HTTP client for Navisworks Routes Server (C# plugin, port 48885).
Analogous to pyRevit Routes client for Revit (port 48884).
"""

NW_BASE = "http://localhost:48885"
NW_TIMEOUT_DEFAULT = 30
NW_TIMEOUT_LONG = 120  # for clash runs, aggregate


def _nw_call(route, method="GET", data=None, timeout=None):
    """
    Make an HTTP call to the Navisworks plugin server.

    Args:
        route:   URL path, e.g. "/status" or "/clash/list"
        method:  "GET" or "POST"
        data:    dict to send as JSON body (POST only)
        timeout: seconds; default varies by method

    Returns:
        dict — JSON response body, or {"error": "..."} on failure
    """
    import requests

    if timeout is None:
        timeout = NW_TIMEOUT_LONG if method == "POST" else NW_TIMEOUT_DEFAULT

    url = NW_BASE + route

    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, json=data or {}, timeout=timeout)
        else:
            return {"error": "Unsupported HTTP method: {}".format(method)}

        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.ConnectionError:
        return {
            "error": (
                "Navisworks не запущен или плагин NW Routes не загружен. "
                "Проверь: curl http://localhost:48885/status"
            )
        }
    except requests.exceptions.Timeout:
        return {"error": "Timeout ({} s) при обращении к Navisworks".format(timeout)}
    except requests.exceptions.HTTPError as e:
        try:
            body = e.response.json()
        except Exception:
            body = {"error": str(e)}
        return body
    except Exception as e:
        return {"error": "Navisworks client error: {}".format(str(e))}


def _nw_is_available():
    """Quick check if the Navisworks plugin is reachable."""
    result = _nw_call("/status", timeout=3)
    return "error" not in result
