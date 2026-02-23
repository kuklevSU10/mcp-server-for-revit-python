# -*- coding: utf-8 -*-
import sys
import asyncio
import requests as _requests
import anyio
from mcp.server.fastmcp import FastMCP, Image, Context
import base64
from typing import Optional, Dict, Any, Union

# Create a generic MCP server for interacting with Revit
# Use stateless_http=True and json_response=True for better compatibility
mcp = FastMCP(
    "Revit MCP Server", 
    host="127.0.0.1", 
    port=8000,
    stateless_http=True,
    json_response=True
)

# Configuration
REVIT_HOST = "localhost"
REVIT_PORT = 48884  # Default pyRevit Routes port
BASE_URL = f"http://{REVIT_HOST}:{REVIT_PORT}/revit_mcp"


async def revit_get(endpoint: str, ctx: Context = None, **kwargs) -> Union[Dict, str]:
    """Simple GET request to Revit API"""
    return await _revit_call("GET", endpoint, ctx=ctx, **kwargs)


async def revit_post(endpoint: str, data: Dict[str, Any], ctx: Context = None, **kwargs) -> Union[Dict, str]:
    """Simple POST request to Revit API"""
    return await _revit_call("POST", endpoint, data=data, ctx=ctx, **kwargs)


async def revit_image(endpoint: str, ctx: Context = None) -> Union[Image, str]:
    """GET request that returns an Image object."""
    def _do():
        response = _requests.get(f"{BASE_URL}{endpoint}", timeout=120.0)
        if response.status_code == 200:
            img_data = base64.b64decode(response.json()["image_data"])
            return ("image", img_data)
        return ("error", f"Error: {response.status_code} - {response.text}")
    try:
        kind, payload = await asyncio.to_thread(_do)
        if kind == "image":
            return Image(data=payload, format="png")
        return payload
    except Exception as e:
        return f"Error: {e}"


async def revit_image_post(endpoint: str, data: Dict, ctx: Context = None) -> Union[Image, str]:
    """POST request that returns an Image object (avoids URL-encoding issues)."""
    def _do():
        response = _requests.post(f"{BASE_URL}{endpoint}", json=data, timeout=120.0)
        if response.status_code == 200:
            img_data = base64.b64decode(response.json()["image_data"])
            return ("image", img_data)
        return ("error", f"Error: {response.status_code} - {response.text}")
    try:
        kind, payload = await asyncio.to_thread(_do)
        if kind == "image":
            return Image(data=payload, format="png")
        return payload
    except Exception as e:
        return f"Error: {e}"


async def _revit_call(method: str, endpoint: str, data: Dict = None, ctx: Context = None,
                      timeout: float = 600.0, params: Dict = None) -> Union[Dict, str]:
    """Internal function — uses requests via thread to avoid httpx/pyRevit incompatibility."""
    def _do():
        url = f"{BASE_URL}{endpoint}"
        if method == "GET":
            r = _requests.get(url, params=params, timeout=timeout)
        else:
            r = _requests.post(url, json=data,
                               headers={"Content-Type": "application/json"},
                               timeout=timeout)
        return r
    try:
        response = await asyncio.to_thread(_do)
        return response.json() if response.status_code == 200 else f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {e}"


# Register all tools BEFORE the main block
from tools import register_tools
register_tools(mcp, revit_get, revit_post, revit_image, revit_image_post)

# Register custom tender tools (SU-10 Analytics)
from custom_tools import register_custom_tools
register_custom_tools(mcp, revit_get, revit_post, revit_image)


async def run_combined_async():
    """Run server with both SSE and streamable-http endpoints.

    This allows clients to connect via either:
    - SSE: GET /sse, POST /messages/
    - Streamable-HTTP: POST/GET /mcp
    """
    import uvicorn

    # Get the streamable-http app first - it has the proper lifespan
    # that initializes the session manager's task group
    http_app = mcp.streamable_http_app()

    # Get SSE routes (SSE doesn't need special lifespan - it creates
    # task groups per-request in connect_sse())
    sse_app = mcp.sse_app()

    # Add SSE routes to the http app (preserving its lifespan)
    for route in sse_app.routes:
        http_app.routes.append(route)

    config = uvicorn.Config(
        http_app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    transport = "stdio"

    if "--sse" in sys.argv:
        transport = "sse"
    elif "--http" in sys.argv or "--streamable-http" in sys.argv:
        transport = "streamable-http"
    elif "--combined" in sys.argv:
        # Run both SSE and streamable-http transports simultaneously
        print("Starting combined server with SSE (/sse, /messages/) and streamable-http (/mcp) endpoints...")
        anyio.run(run_combined_async)
        sys.exit(0)

    mcp.run(transport=transport)