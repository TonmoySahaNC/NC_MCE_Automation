#!/usr/bin/env python3
# before running this script, install required modules:
# pip install requests tzdata backports.zoneinfo

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

# Read year/month, default to current if missing
year_env  = os.getenv("REPORT_YEAR", "").strip()
month_env = os.getenv("REPORT_MONTH", "").strip()
report_year  = int(year_env)  if year_env.isdigit()  else datetime.now().year
report_month = int(month_env) if month_env.isdigit() else datetime.now().month

if not CUSTOMER_ID or not API_KEY:
    raise RuntimeError("CUSTOMER_ID and API_KEY must be set in environment")

# GraphQL queries
query1 = """query { groups { result { name resourceSelectors { resource { name state { status } } } } } }"""
query2 = """query { incomingEvents(limit:500, filter:{filterBy:{field:START_TIME operator:GT values:"2025-05-01T00:00:00"}}) { result { name startTime scheduleTimezone plan { planActions { name resourceGroups { totalNumberOfResources } } } } } }"""
query3 = """
query {
  events(
    limit: 500,
    filter:{filterBy:{field:START_TIME operator:GT values:"2025-04-01T00:00:00"}}
  ) {
    result {
      name
      startTime
      status
      actions {
        actionName
        type
        attempts {
          resourceStates {
            resource {
              name
              provider
              fullCloudResourceId
            }
            status
            annotation
          }
        }
      }
    }
  }
}"""
queries = {"1": query1, "2": query2, "3": query3}

if QUERY not in queries:
    print(f"Invalid QUERY '{QUERY}'. Must be one of 1, 2, or 3.")
    sys.exit(1)

# Timezone support
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
ist_zone = ZoneInfo("Asia/Kolkata")

API_URL = "https://api.fleetcontrol.nordcloudapp.com/graphql"
all_rows = []

# Fetch data
print(f"---- Processing {CUSTOMER_NAME} for {report_year}-{report_month:02d} ----")
resp = requests.post(
    API_URL,
    headers={
        "Content-Type":  "application/json",
        "X-Api-Key":     API_KEY,
        "X-Customer-ID": CUSTOMER_ID,
        "Accept":        "application/json",
    },
    json={"query": queries[QUERY]}
)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)
data = resp.json().get("data", {})

# === Query 1 ===
if QUERY == "1":
    for g in data.get("groups", {}).get("result", []):
        for sel in g.get("resourceSelectors", []):
            r = sel.get("resource", {})
            if r.get("state", {}).get("status") == "CONNECTION_LOST":
                all_rows.append({
                    "Customer":       CUSTOMER_NAME,
                    "Resource Group": g.get("name", ""),
                    "Resource Name":  r.get("name", ""),
                    "Status":         "CONNECTION_LOST"
                })

# === Query 2 ===
elif QUERY == "2":
    for ev in data.get("incomingEvents", {}).get("result", []):
        st = ev.get("startTime")
        if not st:
            continue
        dt = datetime.fromisoformat(st)
        tz = ZoneInfo(ev.get("scheduleTimezone", "UTC"))
        dt_ist = dt.astimezone(tz).astimezone(ist_zone)
        if dt_ist.year == report_year and dt_ist.month == report_month:
            patch_count = 0
            for act in ev.get("plan", {}).get("planActions", []):
                if act.get("name", "").lower() == "patch":
                    patch_count = sum(
                        rg.get("totalNumberOfResources", 0)
                        for rg in act.get("resourceGroups", [])
                    )
            all_rows.append({
                "Customer":        CUSTOMER_NAME,
                "Plan Name":       ev.get("name", ""),
                "Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                "Timezone":        ev.get("scheduleTimezone", "UTC"),
                "Resource Count":  patch_count
            })

# === Query 3 ===
else:
    for ev in data.get("events", {}).get("result", []):
        st = ev.get("startTime")
        if not st:
            continue
        dt_ist = datetime.fromisoformat(st).astimezone(ist_zone)
        if not (dt_ist.year == report_year and dt_ist.month == report_month):
            continue

        for act in ev.get("actions", []):
            action_name = act.get("actionName", "").lower()
            action_type = act.get("type", "").upper()

            # Always include 'patch'
            if action_name == "patch":
                include = True
            # For Heineken only, include any action of type CUSTOM
            elif CUSTOMER_NAME.lower() == "heineken" and action_type == "CUSTOM":
                include = True
            else:
                include = False

            if not include:
                continue

            # Add each resource state row
            for rs in act.get("attempts", []):
                for state in rs.get("resourceStates", []):
                    res = state.get("resource") or {}
                    all_rows.append({
                        "Customer":               CUSTOMER_NAME,
                        "Event Name":             ev.get("name", ""),
                        "Event Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                        "ActionName":             act.get("actionName", ""),
                        "ResourceName":           res.get("name", ""),
                        "ResourceStatus":         state.get("status", ""),
                        "Annotation":             state.get("annotation", ""),
                        "Provider":               res.get("provider", ""),
                        "FullResourceID":         res.get("fullCloudResourceId", "")
                    })

# === Write CSV ===
if not all_rows:
    print("No data found.")
    sys.exit(0)

abbr = calendar.month_abbr[report_month].lower()
if QUERY == "1":
    fn = f"{CUSTOMER_NAME}_connection_lost.csv"
elif QUERY == "2":
    fn = f"{CUSTOMER_NAME}_incoming_events_{report_year}_{abbr}.csv"
else:
    fn = f"{CUSTOMER_NAME}_events_{report_year}_{abbr}_patch.csv"

with open(fn, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Created CSV: {fn} ({len(all_rows)} rows)")
