# -*- coding: utf-8 -*-
"""BIM Catalog — scans all categories and returns element types with metrics."""
import json
from mcp.server.fastmcp import Context
from ._constants import (
    CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M, MAX_BATCH_SIZE,
    ALL_CATEGORIES, CAT_BATCHES,
)
from ._linked_files import build_linked_files_code, build_linked_batch_code
from ._scan_engine import _build_batch_code


def register_bim_catalog_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM catalog tools."""

    @mcp_server.tool()
    async def bim_catalog(
        categories: list[str] = None,
        include_params: bool = False,
        include_links: bool = False,
        ctx: Context = None,
    ) -> dict:
        """Scan ALL categories of BIM model. Returns all element types with metrics.

        categories: list of category names (None = scan all 30+ categories)
        include_params: include sample type parameters in output
        include_links: if True, also scan all loaded linked .rvt files.
                       Returns {"host": {...}, "linked_files": {"file.rvt": {...}}}
        Returns: {CategoryName: {total_count, total_volume_m3, total_area_m2, types: [...]}}
        """
        if categories is not None:
            # Custom category list — single batch
            batches = [categories]
        else:
            batches = CAT_BATCHES

        all_results = {}
        for batch in batches:
            # Filter to valid categories
            valid_batch = [c for c in batch if c in ALL_CATEGORIES]
            if not valid_batch:
                continue
            code = _build_batch_code(valid_batch, ALL_CATEGORIES, include_params)
            resp = await revit_post("/execute_code/", {"code": code}, ctx)
            if isinstance(resp, dict) and resp.get("status") == "success":
                raw = resp.get("output", "{}").strip()
                try:
                    batch_result = json.loads(raw)
                    all_results.update(batch_result)
                except Exception as e:
                    all_results["_error_batch_{}".format(batch[0])] = str(e)

        total_elements = sum(v.get("total_count", 0) for v in all_results.values()
                             if isinstance(v, dict) and "total_count" in v)
        cats_with_data = sum(1 for v in all_results.values()
                             if isinstance(v, dict) and v.get("total_count", 0) > 0)
        all_results["_meta"] = {
            "total_elements": total_elements,
            "categories_scanned": len(batches) * 5,
            "categories_with_data": cats_with_data,
            "scan_time_note": "Use include_params=True for richer data",
        }

        if not include_links:
            return all_results

        # --- Wrap host result and add linked_files section ---
        result = {"host": all_results, "linked_files": {}}

        # Discover linked files
        links_code = build_linked_files_code()
        links_resp = await revit_post("/execute_code/", {"code": links_code}, ctx)
        if not isinstance(links_resp, dict) or links_resp.get("status") != "success":
            result["_links_error"] = "Could not retrieve linked files list"
            return result

        links_raw = links_resp.get("output", "[]").strip()
        try:
            links_list = json.loads(links_raw)
        except Exception as e:
            result["_links_error"] = "JSON parse error: " + str(e)
            return result

        # Scan each loaded linked file using the same category list
        all_link_cats = list(CATEGORY_REGISTRY.keys())
        for link_info in links_list:
            if not link_info.get("loaded"):
                continue
            link_title = link_info["name"]
            link_results = {}

            for i in range(0, len(all_link_cats), MAX_BATCH_SIZE):
                batch = all_link_cats[i: i + MAX_BATCH_SIZE]
                code = build_linked_batch_code(batch, link_title)
                resp = await revit_post("/execute_code/", {"code": code}, ctx)
                if not isinstance(resp, dict) or resp.get("status") != "success":
                    continue
                raw = resp.get("output", "{}").strip()
                try:
                    batch_result = json.loads(raw)
                    if "_error" not in batch_result:
                        link_results.update(batch_result)
                except Exception:
                    pass

            if link_results:
                link_elem_count = sum(
                    v.get("total_count", 0) for v in link_results.values()
                    if isinstance(v, dict) and "total_count" in v
                )
                link_results["_meta"] = {
                    "link_title": link_title,
                    "total_elements": link_elem_count,
                }
                result["linked_files"][link_title] = link_results

        return result
