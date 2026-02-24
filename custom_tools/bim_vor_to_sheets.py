# DEPRECATED: используй bim_export вместо этого инструмента.
# -*- coding: utf-8 -*-
"""BIM → VOR → Google Sheets export tool."""
import json
import os
import datetime
from mcp.server.fastmcp import Context
from ._constants import ironpython_cat_map, CAT_OST_MAP

_GWORKSPACE_DIR = r"C:\Users\kuklev.d.s\clawd\.gworkspace"
_TOKEN_PATH = os.path.join(_GWORKSPACE_DIR, "token.json")
_CREDS_PATH = os.path.join(_GWORKSPACE_DIR, ".gworkspace-credentials.json")
_OAUTH_KEYS_PATH = os.path.join(_GWORKSPACE_DIR, "gcp-oauth.keys.json")

_MAPPINGS_DIR = os.path.join(os.path.dirname(__file__), "mappings")


def _get_sheets_service():
    """Build authenticated Google Sheets service.

    Tries token.json first, then falls back to .gworkspace-credentials.json.
    Returns service object or raises RuntimeError with auth message.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "google-api-python-client not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        )

    # Load OAuth client credentials (client_id + client_secret)
    client_id = None
    client_secret = None
    if os.path.exists(_OAUTH_KEYS_PATH):
        with open(_OAUTH_KEYS_PATH, encoding="utf-8") as f:
            oauth_data = json.load(f)
        installed = oauth_data.get("installed") or oauth_data.get("web") or {}
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret")

    # Determine token source
    token_source = None
    if os.path.exists(_TOKEN_PATH):
        token_source = _TOKEN_PATH
    elif os.path.exists(_CREDS_PATH):
        token_source = _CREDS_PATH

    if not token_source:
        raise RuntimeError(
            "Google Sheets not authenticated. Please re-authorize via mcporter."
        )

    with open(token_source, encoding="utf-8") as f:
        token_data = json.load(f)

    # Build Credentials object
    scopes = token_data.get("scopes") or token_data.get("scope", "").split()
    if isinstance(scopes, str):
        scopes = scopes.split()
    # Ensure Sheets scope is present
    if not any("spreadsheets" in s for s in scopes):
        scopes.append("https://www.googleapis.com/auth/spreadsheets")

    creds = Credentials(
        token=token_data.get("access_token") or token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id") or client_id,
        client_secret=token_data.get("client_secret") or client_secret,
        scopes=scopes,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("sheets", "v4", credentials=creds)


def _hex_to_rgb(hex_color):
    """Convert #RRGGBB to {red, green, blue} dict with 0-1 float values."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}


def _load_mapping(name):
    path = os.path.join(_MAPPINGS_DIR, "{}_mapping.json".format(name))
    if not os.path.exists(path):
        raise FileNotFoundError("Mapping not found: {}".format(path))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def _get_bim_vor_data(mapping, revit_post, ctx):
    """Fetch BIM volumes and map to VOR positions (mirrors bim_to_vor logic)."""
    try:
        mapping_data = _load_mapping(mapping)
    except FileNotFoundError as e:
        return None, str(e)

    positions_cfg = mapping_data.get("positions", [])
    needed_cats = list({
        p["bim_category"]
        for p in positions_cfg
        if p.get("bim_category")
    })

    bim_data = {}
    if needed_cats:
        cats_repr = repr(needed_cats)
        code = (
            "import json\n"
            + ironpython_cat_map(list(CAT_OST_MAP.keys())) + "\n"
            "FT3_TO_M3 = 0.028316846592\n"
            "FT2_TO_M2 = 0.09290304\n"
            "categories = " + cats_repr + "\n"
            "result = {}\n"
            "for cat_name in categories:\n"
            "    if cat_name not in CAT_MAP:\n"
            "        continue\n"
            "    bic = CAT_MAP[cat_name]\n"
            "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
            ".WhereElementIsNotElementType().ToElements()\n"
            "    totals = {'count': 0, 'volume_m3': 0.0, 'area_m2': 0.0}\n"
            "    for elem in elems:\n"
            "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
            "        ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)\n"
            "        totals['volume_m3'] += (vp.AsDouble() if vp and vp.HasValue else 0.0) * FT3_TO_M3\n"
            "        totals['area_m2'] += (ap.AsDouble() if ap and ap.HasValue else 0.0) * FT2_TO_M2\n"
            "        totals['count'] += 1\n"
            "    result[cat_name] = totals\n"
            "print(json.dumps(result))\n"
        )
        response = await revit_post("/execute_code/", {"code": code}, ctx)
        if isinstance(response, dict) and response.get("status") == "success":
            try:
                bim_data = json.loads(response.get("output", "{}").strip())
            except Exception:
                pass

    positions = []
    for pos in positions_cfg:
        cat = pos.get("bim_category")
        use_area = pos.get("use_area", False)
        use_count = pos.get("use_count", False)
        manual = pos.get("manual_volume")

        if cat and cat in bim_data:
            cat_data = bim_data[cat]
            if use_count:
                volume = cat_data.get("count", 0)
            elif use_area:
                volume = round(cat_data.get("area_m2", 0.0), 3)
            else:
                volume = round(cat_data.get("volume_m3", 0.0), 3)
            source = "BIM:{}".format(cat)
        elif manual is not None:
            volume = manual
            source = "manual"
        else:
            volume = None
            source = "missing"

        positions.append({
            "vor_id": pos.get("vor_id"),
            "name": pos.get("name"),
            "unit": pos.get("unit"),
            "volume": volume,
            "source": source,
        })

    return positions, None


def _build_format_requests(sheet_id, num_rows):
    """Build batchUpdate requests for header + alternating row formatting."""
    COLOR_HEADER_BG = _hex_to_rgb("#1565C0")
    COLOR_HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}
    COLOR_ALT_ROW = _hex_to_rgb("#E8F4FD")
    COLOR_WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
    # Column widths in pixels (approx chars * 7): 5, 50, 10, 15, 40
    COL_WIDTHS = [40, 350, 70, 105, 280]

    requests = []

    # Header row: bold, blue bg, white text
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER_BG,
                    "textFormat": {"bold": True, "foregroundColor": COLOR_HEADER_FG},
                    "horizontalAlignment": "CENTER",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    })

    # Alternating rows
    for i in range(num_rows):
        row_idx = i + 1  # 0 = header
        bg = COLOR_ALT_ROW if i % 2 == 1 else COLOR_WHITE
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": row_idx,
                          "endRowIndex": row_idx + 1,
                          "startColumnIndex": 0, "endColumnIndex": 5},
                "cell": {"userEnteredFormat": {"backgroundColor": bg}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    # Number format for column D (Объём BIM) — column index 3
    if num_rows > 0:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1,
                          "endRowIndex": num_rows + 1,
                          "startColumnIndex": 3, "endColumnIndex": 4},
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "NUMBER", "pattern": "0.00"}
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        })

    # Column widths
    for col_idx, width_px in enumerate(COL_WIDTHS):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": col_idx, "endIndex": col_idx + 1},
                "properties": {"pixelSize": width_px},
                "fields": "pixelSize",
            }
        })

    # Freeze header row
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    return requests


def register_bim_vor_to_sheets_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register bim_vor_to_sheets tool with the MCP server."""

    @mcp_server.tool()
    async def bim_vor_to_sheets(
        spreadsheet_id: str = "",
        sheet_name: str = "ВОР из BIM",
        mapping: str = "default",
        ctx: Context = None,
    ) -> dict:
        """Export BIM volumes to VOR format in Google Sheets.

        Args:
            spreadsheet_id: existing spreadsheet ID, or empty to create new
            sheet_name: name of the sheet/tab to write to
            mapping: VOR mapping name (file in custom_tools/mappings/)

        Returns:
            {"spreadsheet_id": "...", "url": "https://docs.google.com/...",
             "rows_written": 42, "mapping": "default"}
        """
        # 1. Authenticate
        try:
            service = _get_sheets_service()
        except RuntimeError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": "Sheets auth error: {}".format(str(e))}

        sheets_api = service.spreadsheets()

        # 2. Fetch BIM data
        positions, err = await _get_bim_vor_data(mapping, revit_post, ctx)
        if err:
            return {"error": err}
        if not positions:
            return {"error": "No positions returned from BIM mapping"}

        # 3. Create or open spreadsheet
        if not spreadsheet_id:
            today = datetime.date.today().strftime("%d.%m.%Y")
            title = "ВОР {} ({})".format(today, mapping)
            new_ss = sheets_api.create(body={
                "properties": {"title": title},
                "sheets": [{"properties": {"title": sheet_name}}],
            }).execute()
            spreadsheet_id = new_ss["spreadsheetId"]
            # Sheet was just created, get its ID
            sheet_id = new_ss["sheets"][0]["properties"]["sheetId"]
        else:
            # Check if sheet tab exists; create if missing
            meta = sheets_api.get(spreadsheetId=spreadsheet_id).execute()
            existing = {s["properties"]["title"]: s["properties"]["sheetId"]
                        for s in meta.get("sheets", [])}
            if sheet_name not in existing:
                resp = sheets_api.batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [{"addSheet": {
                        "properties": {"title": sheet_name}
                    }}]}
                ).execute()
                sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
            else:
                sheet_id = existing[sheet_name]

        # 4. Clear sheet contents
        range_all = "{}!A1:Z1000".format(sheet_name)
        sheets_api.values().clear(
            spreadsheetId=spreadsheet_id, range=range_all, body={}
        ).execute()

        # 5. Write headers + data rows
        headers = ["#", "Наименование работ", "Ед.изм.", "Объём BIM", "Источник"]
        rows = [headers]
        for i, pos in enumerate(positions, start=1):
            vol = pos.get("volume")
            rows.append([
                pos.get("vor_id") or str(i),
                pos.get("name") or "",
                pos.get("unit") or "",
                vol if vol is not None else "",
                pos.get("source") or "",
            ])

        sheets_api.values().update(
            spreadsheetId=spreadsheet_id,
            range="{}!A1".format(sheet_name),
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()

        # 6. Apply formatting
        fmt_requests = _build_format_requests(sheet_id, len(positions))
        if fmt_requests:
            sheets_api.batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": fmt_requests},
            ).execute()

        url = "https://docs.google.com/spreadsheets/d/{}/edit".format(spreadsheet_id)
        return {
            "spreadsheet_id": spreadsheet_id,
            "url": url,
            "rows_written": len(positions),
            "mapping": mapping,
            "sheet_name": sheet_name,
        }
