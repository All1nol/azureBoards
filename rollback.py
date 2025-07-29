import requests 
import base64
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

PAT =  os.getenv('PAT')
ORG =  os.getenv('ORG') 
PROJECT =  os.getenv('PROJECT')
ITEM_IDS = list(range(1,102))

TZ_OFFSET = timedelta(hours=4)
TODAY_START_LOCAL = datetime(2025, 7, 28, 0, 0, 0, tzinfo=timezone(TZ_OFFSET))
TODAY_START_UTC   = TODAY_START_LOCAL.astimezone(timezone.utc)
AS_OF_STR = TODAY_START_UTC.strftime('%Y-%m-%dT%H:%M:%SZ')
print(f"Rolling back each item to state as of before {AS_OF_STR} (UTC)")

# API headers
auth = base64.b64encode(f":{PAT}".encode()).decode()
HEADERS = {"Authorization": f"Basic {auth}"}

# PATCH-UNSAFE SYSTEM FIELDS (known to always fail)
SKIP_FIELDS = {
    "System.BoardColumn", "System.BoardColumnDone", "System.Id", "System.Rev", "System.CreatedDate", "System.CreatedBy",
    "System.ChangedDate", "System.ChangedBy", "System.CommentCount", "System.TeamProject", "System.WorkItemType",
    "System.Watermark", "System.History"
    # You can add fields seen in new PATCH errors if needed.
}

DO_ROLLBACK = True   # Set False for dry run, True to PATCH/restore!

for work_item in ITEM_IDS:
    print("="*70)
    print(f"Work Item {work_item}")

    # Get full revision history for this item
    url = f"https://dev.azure.com/{ORG}/{PROJECT}/_apis/wit/workItems/{work_item}/revisions?api-version=7.1"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"  ERROR: {resp.status_code} {resp.text}")
        continue

    revs = resp.json().get("value", [])
    # Find the latest (max) rev whose ChangedDate < AS_OF_STR
    matching_revs = [r for r in revs if r["fields"]["System.ChangedDate"] < AS_OF_STR]
    if not matching_revs:
        print("  No revision before pre-today cut-off found.")
        continue

    rev = max(matching_revs, key=lambda r: r["fields"]["System.ChangedDate"])
    print(f"  Latest pre-today revision: {rev['fields']['System.ChangedDate']}")

    patch_body = []
    for field, value in rev['fields'].items():
        if field not in SKIP_FIELDS:
            patch_body.append({
                "op": "replace",
                "path": f"/fields/{field}",
                "value": value
            })

    print(f"  Would restore {len(patch_body)} fields (e.g. System.AssignedTo, System.Tags if present):")
    for op in patch_body:
        print(f"    {op['path']} = {op['value']!r}")

    # Only PATCH if enabled and something to patch
    if DO_ROLLBACK and patch_body:
        patch_url = f"https://dev.azure.com/{ORG}/{PROJECT}/_apis/wit/workItems/{work_item}?api-version=7.1"
        headers = {**HEADERS, "Content-Type": "application/json-patch+json"}
        patch_resp = requests.patch(patch_url, headers=headers, json=patch_body)
        if patch_resp.status_code == 200:
            print("  ✅ Successfully rolled back.")
        else:
            print(f"  ❌ PATCH FAILED: {patch_resp.status_code}: {patch_resp.text}")
print("\nDone!")
