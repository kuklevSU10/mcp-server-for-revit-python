# -*- coding: utf-8 -*-
"""BIM Linked Files tools — list and scan linked .rvt documents."""
import json
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, MAX_BATCH_SIZE
from ._linked_files import build_linked_files_code, build_linked_batch_code


def _make_batches(cat_list, size):
    """Split cat_list into sub-lists of at most `size` elements."""
    for i in range(0, len(cat_list), size):
        yield cat_list[i: i + size]


def register_bim_links_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM linked-files tools with the MCP server."""

    @mcp_server.tool()
    async def list_linked_files(ctx: Context = None) -> dict:
        """List all linked Revit files (.rvt) in the currently open project.

        Returns a dict with a 'links' list. Each entry:
        {name: str, loaded: bool, path: str, element_count: int}
        Unloaded links have element_count = 0 and path = ''.
        """
        code = build_linked_files_code()
        resp = await revit_post("/execute_code/", {"code": code}, ctx)
        if not isinstance(resp, dict) or resp.get("status") != "success":
            return {"error": "Revit did not return success", "response": str(resp)}

        raw = resp.get("output", "[]").strip()
        try:
            links = json.loads(raw)
        except Exception as e:
            return {"error": "JSON parse error: " + str(e), "raw": raw}

        loaded   = [lk for lk in links if lk.get("loaded")]
        unloaded = [lk for lk in links if not lk.get("loaded")]
        return {
            "total": len(links),
            "loaded": len(loaded),
            "unloaded": len(unloaded),
            "links": links,
        }

    @mcp_server.tool()
    async def bim_catalog_linked(
        link_title: str,
        categories: str = "all",
        ctx: Context = None,
    ) -> dict:
        """Scan element categories inside a specific linked Revit file.

        link_title: exact Title of the linked document (use list_linked_files to find it)
        categories: comma-separated category names, or 'all' to scan every known category.
                    Valid names: Walls, Floors, Roofs, Columns, Beams, Foundations, Doors,
                    Windows, Furniture, Ducts, Pipes, MechanicalEquipment, etc.

        Returns:
        {
          "link_title": str,
          "categories": {
            "Walls": {"total_count": N, "total_volume_m3": X, "types": [...]},
            ...
          },
          "_meta": {"categories_scanned": N, "categories_with_data": M}
        }
        """
        # --- resolve category list ---
        if categories.strip().lower() == "all":
            cat_list = list(CATEGORY_REGISTRY.keys())
        else:
            cat_list = [c.strip() for c in categories.split(",") if c.strip()]
            # filter to known
            cat_list = [c for c in cat_list if c in CATEGORY_REGISTRY]
            if not cat_list:
                return {"error": "No valid categories specified", "link_title": link_title}

        # --- scan in batches ---
        all_cat_results = {}
        for batch in _make_batches(cat_list, MAX_BATCH_SIZE):
            code = build_linked_batch_code(batch, link_title)
            resp = await revit_post("/execute_code/", {"code": code}, ctx)
            if not isinstance(resp, dict) or resp.get("status") != "success":
                all_cat_results["_error_batch_{}".format(batch[0])] = str(resp)
                continue
            raw = resp.get("output", "{}").strip()
            try:
                batch_result = json.loads(raw)
                # Check if the linked file was not found
                if "_error" in batch_result:
                    return {"error": batch_result["_error"], "link_title": link_title}
                all_cat_results.update(batch_result)
            except Exception as e:
                all_cat_results["_parse_error_{}".format(batch[0])] = str(e)

        # --- build meta ---
        cats_with_data = sum(
            1 for v in all_cat_results.values()
            if isinstance(v, dict) and v.get("total_count", 0) > 0
        )
        total_elements = sum(
            v.get("total_count", 0)
            for v in all_cat_results.values()
            if isinstance(v, dict) and "total_count" in v
        )

        return {
            "link_title": link_title,
            "categories": all_cat_results,
            "_meta": {
                "categories_scanned": len(cat_list),
                "categories_with_data": cats_with_data,
                "total_elements": total_elements,
            },
        }
