# -*- coding: utf-8 -*-
"""View-related tools for capturing and listing Revit views"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_view_tools(mcp, revit_get, revit_post, revit_image, revit_image_post=None):
    """Register view-related tools"""

    @mcp.tool()
    async def get_revit_view(view_name: str, ctx: Context = None):
        """Export a specific Revit view as an image (supports Cyrillic view names)."""
        import base64
        from mcp.server.fastmcp import Image

        # Use execute_code to export the view — avoids all URL encoding issues
        code = (
            "import json, base64, os, tempfile\n"
            "from System.Collections.Generic import List\n"
            "target_vn = " + repr(view_name) + "\n"
            "all_views = list(DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements())\n"
            "target_view = None\n"
            "for v in all_views:\n"
            "    try:\n"
            "        n = v.Name\n"
            "        if isinstance(n, unicode): n = n.strip()\n"
            "        else: n = n.decode('utf-8','r').strip()\n"
            "        if n == target_vn: target_view = v; break\n"
            "    except: pass\n"
            "if target_view is None:\n"
            "    print(json.dumps({'error': 'View not found: ' + target_vn}))\n"
            "else:\n"
            "    out = os.path.join(tempfile.gettempdir(), 'RevitMCPExports')\n"
            "    if not os.path.exists(out): os.makedirs(out)\n"
            "    ieo = DB.ImageExportOptions()\n"
            "    ieo.ExportRange = DB.ExportRange.SetOfViews\n"
            "    ids = List[DB.ElementId]()\n"
            "    ids.Add(target_view.Id)\n"
            "    ieo.SetViewsAndSheets(ids)\n"
            "    ieo.FilePath = os.path.join(out, 'view_export')\n"
            "    ieo.HLRandWFViewsFileType = DB.ImageFileType.PNG\n"
            "    ieo.ShadowViewsFileType = DB.ImageFileType.PNG\n"
            "    ieo.ImageResolution = DB.ImageResolution.DPI_150\n"
            "    ieo.ZoomType = DB.ZoomFitType.FitToPage\n"
            "    ieo.PixelSize = 1024\n"
            "    doc.ExportImage(ieo)\n"
            "    pngs = sorted([os.path.join(out,f) for f in os.listdir(out) if f.endswith('.png')],\n"
            "                  key=lambda x: os.path.getctime(x), reverse=True)\n"
            "    if pngs:\n"
            "        with open(pngs[0],'rb') as f: data=f.read()\n"
            "        try: os.remove(pngs[0])\n"
            "        except: pass\n"
            "        print(json.dumps({'image_b64': base64.b64encode(data).decode('utf-8'), 'size': len(data)}))\n"
            "    else:\n"
            "        print(json.dumps({'error': 'Export produced no PNG'}))\n"
        )
        resp = await revit_post("/execute_code/", {"code": code}, ctx)
        if isinstance(resp, str) and resp.startswith("Error"):
            return resp
        try:
            import json as _json
            output = resp.get("output", "") if isinstance(resp, dict) else str(resp)
            # extract the last JSON line from output
            for line in reversed(output.strip().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    parsed = _json.loads(line)
                    if "error" in parsed:
                        return f"View export error: {parsed['error']}"
                    img_bytes = base64.b64decode(parsed["image_b64"])
                    return Image(data=img_bytes, format="png")
            return f"View export failed: no JSON in output. Raw: {output[:200]}"
        except Exception as e:
            return f"View export parse error: {e} | resp: {str(resp)[:200]}"

    @mcp.tool()
    async def list_revit_views(ctx: Context = None) -> str:
        """Get a list of all exportable views in the current Revit model"""
        response = await revit_get("/list_views/", ctx)
        return format_response(response)

    @mcp.tool()
    async def get_current_view_info(ctx: Context = None) -> str:
        """
        Get detailed information about the currently active view in Revit.

        Returns comprehensive information including:
        - View name, type, and ID
        - Scale and detail level
        - Crop box status
        - View family type
        - View discipline
        - Template status
        """
        if ctx:
            await ctx.info("Getting current view information...")
        response = await revit_get("/current_view_info/", ctx)
        return format_response(response)

    @mcp.tool()
    async def get_current_view_elements(ctx: Context = None) -> str:
        """
        Get all elements visible in the currently active view in Revit.

        Returns detailed information about each element including:
        - Element ID, name, and type
        - Category and category ID
        - Level information (if applicable)
        - Location information (point or curve)
        - Summary statistics grouped by category

        This is useful for understanding what elements are currently visible
        and analyzing the content of the active view.
        """
        if ctx:
            await ctx.info("Getting elements in current view...")
        response = await revit_get("/current_view_elements/", ctx)
        return format_response(response)
