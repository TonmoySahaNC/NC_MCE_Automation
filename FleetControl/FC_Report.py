#!/usr/bin/env python3
# before running this script, install required modules:
# pip install requests tzdata

import os
import sys
import requests
import csv
import calendar
from datetime import datetime

# === Read settings from environment ===
CUSTOMER_ID   = os.getenv("CUSTOMER_ID")
API_KEY       = os.getenv("API_KEY")
CUSTOMER_NAME = os.getenv("CUSTOMER_NAME", CUSTOMER_ID)
QUERY         = os.getenv("QUERY", "3")  # default to query 3

if not CUSTOMER_ID or not API_KEY:
    raise RuntimeError("Both CUSTOMER_ID and API_KEY must be set in environment")

# Define your GraphQL queries
query1 = """query { groups { result { name resourceSelectors { resource { name state { status } } } } } }"""
query2 = """query { incomingEvents(limit:500, filter:{filterBy:{field:START_TIME operator:GT values:"2025-01-01T00:00:00"}}) { result { name startTime scheduleTimezone plan { planActions { name resourceGroups { totalNumberOfResources } } } } } }"""
query3 = """query { events(limit:500, filter:{filterBy:{field:START_TIME operator:GT values:"2025-02-01T00:00:00"}}) { result { name startTime status actions { actionName attempts { resourceStates { resource { name provider fullCloudResourceId } status annotation } } } } } }"""

queries = {"1": query1, "2": query2, "3": query3}
if QUERY not in queries:
    print(f"Invalid QUERY '{QUERY}'. Must be one of 1, 2, 3.")
    sys.exit(1)

# Optional parameters for query 2/3
report_year = report_month = None
if QUERY in ["2", "3"]:
    # You can also pass YEAR/MONTH via env if you like; default to now
    report_year  = int(os.getenv("REPORT_YEAR", datetime.now().year))
    report_month = int(os.getenv("REPORT_MONTH", datetime.now().month))

# Timezone support
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
ist_zone = ZoneInfo("Asia/Kolkata")

API_URL = "https://api.fleetcontrol.nordcloudapp.com/graphql"
all_rows = []

# Single customer run
print(f"---- Processing {CUSTOMER_NAME} (ID={CUSTOMER_ID}) ----")
headers = {
    "Content-Type":    "application/json",
    "X-Api-Key":       API_KEY,
    "X-Customer-ID":   CUSTOMER_ID,
    "Accept":          "application/json",
}
response = requests.post(API_URL, headers=headers, json={"query": queries[QUERY]})
if response.status_code != 200:
    print(f"HTTP {response.status_code} error: {response.text}")
    sys.exit(1)

data = response.json().get("data") or {}
if QUERY == "1":
    groups = data.get("groups", {}).get("result", [])
    for g in groups:
        for sel in g.get("resourceSelectors", []):
            r = sel.get("resource", {})
            if r.get("state",{}).get("status") == "CONNECTION_LOST":
                all_rows.append({
                    "Customer": CUSTOMER_NAME,
                    "Resource Group": g.get("name",""),
                    "Resource Name": r.get("name",""),
                    "Status": "CONNECTION_LOST",
                })

elif QUERY == "2":
    events = data.get("incomingEvents",{}).get("result", [])
    for ev in events:
        st = ev.get("startTime")
        if not st: continue
        dt = datetime.fromisoformat(st)
        tz = ZoneInfo(ev.get("scheduleTimezone","UTC"))
        dt_ist = dt.astimezone(tz).astimezone(ist_zone)
        if dt_ist.year==report_year and dt_ist.month==report_month:
            patch_count = 0
            for act in ev.get("plan",{}).get("planActions",[]):
                if act.get("name","").lower()=="patch":
                    patch_count = sum(rg.get("totalNumberOfResources",0)
                                       for rg in act.get("resourceGroups",[]))
            all_rows.append({
                "Customer": CUSTOMER_NAME,
                "Plan Name": ev.get("name",""),
                "Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                "Timezone": ev.get("scheduleTimezone","UTC"),
                "Resource Count": patch_count
            })

else:  # QUERY == "3"
    events = data.get("events",{}).get("result", [])
    for ev in events:
        st = ev.get("startTime")
        if not st: continue
        dt_ist = datetime.fromisoformat(st).astimezone(ist_zone)
        if dt_ist.year==report_year and dt_ist.month==report_month:
            for act in ev.get("actions",[]):
                if act.get("actionName","").lower()=="patch":
                    for att in act.get("attempts",[]):
                        for rs in att.get("resourceStates",[]):
                            res = rs.get("resource") or {}
                            all_rows.append({
                                "Customer": CUSTOMER_NAME,
                                "Event Name": ev.get("name",""),
                                "Event Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                                "ActionName": act.get("actionName",""),
                                "ResourceName": res.get("name",""),
                                "ResourceStatus": rs.get("status",""),
                                "Annotation": rs.get("annotation",""),
                                "Provider": res.get("provider",""),
                                "FullResourceID": res.get("fullCloudResourceId","")
                            })

# Write CSV
if not all_rows:
    print("No data found.")
    sys.exit(0)

# Determine filename
month_abbr = calendar.month_abbr[report_month].lower() if report_month else ""
if QUERY=="1":
    csv_fn = f"{CUSTOMER_NAME}_connection_lost.csv"
elif QUERY=="2":
    csv_fn = f"{CUSTOMER_NAME}_incoming_events_{report_year}_{month_abbr}.csv"
else:
    csv_fn = f"{CUSTOMER_NAME}_events_{report_year}_{month_abbr}_patch.csv"

with open(csv_fn,"w",newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Created CSV: {csv_fn} ({len(all_rows)} rows)")
