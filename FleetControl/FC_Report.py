#!/usr/bin/env python3
# before running this script, install required modules:
# pip install requests tzdata

import requests
import json
import csv
import os
import calendar
from datetime import datetime

# Load API keys from environment (GitHub Actions secrets)
customers = {
    "1": {"CUSTOMER": "Brother","CUSTOMER_ID": "8292fa9a-abef-4173-a22b-ac2e2c8df4bd","API_KEY": os.getenv("BROTHER_API_KEY")},
    "2": {"CUSTOMER": "Grohe","CUSTOMER_ID": "940165de-1711-4053-88d6-23e588cc1593","API_KEY": os.getenv("GROHE_API_KEY")},
    "3": {"CUSTOMER": "Heineken","CUSTOMER_ID": "a6cabac5-8168-417b-a4bb-a876c955aa3f","API_KEY": os.getenv("HEINEKEN_API_KEY")},
    "4": {"CUSTOMER": "Neste","CUSTOMER_ID": "3de03704-e850-4cfa-ba2e-7137ae33689f","API_KEY": os.getenv("NESTE_API_KEY")},
    "5": {"CUSTOMER": "Sandvik","CUSTOMER_ID": "5710c478-2f02-4335-a20a-349823e81f1d","API_KEY": os.getenv("SANDVIK_API_KEY")},
    "6": {"CUSTOMER": "Thames","CUSTOMER_ID": "bdbc97ab-add5-4d37-afa6-5ebb7435eb3f","API_KEY": os.getenv("THAMES_API_KEY")}
}


for cust_id, info in customers.items():
    if info["API_KEY"] is None:
        raise RuntimeError(
            f"Missing API key for customer '{info['CUSTOMER']}' (ID={cust_id}). "
            "Make sure the corresponding GitHub secret is defined."
        )

print("Select a customer by entering the corresponding number:")
print(" 0 -> All")
for cid, info in customers.items():
    print(f" {cid} -> {info['CUSTOMER']}")
selected = input("Enter the customer number (0-6): ").strip()

if selected != "0" and selected not in customers:
    print("Invalid selection. Exiting.")
    exit(1)

query1 = """
query {
    groups {
        result {
            name
            resourceSelectors {
                resource {
                    name
                    state {
                        status
                    }
                }
            }
        }
    }
}
"""

query2 = """
query {
  incomingEvents (
    limit: 500
    filter: {
      filterBy:{field:START_TIME operator:GT values:"2025-01-01T00:00:00"}
    }
  ) {
    result {
      name
      startTime
      scheduleTimezone
      plan { planActions { name, resourceGroups { totalNumberOfResources } } }
      estimatedEndTime
      status
    }
    pageInfo {
      count
    }
  }
}
"""

query3 = """
query {
  events(
    limit: 500
    filter: {
      filterBy:{field:START_TIME operator:GT values:"2025-02-01T00:00:00"}
    }
  ) {
    result {
      name
      startTime
      status
      actions {
        actionName
        type
        globalState { status }
        attempts {
          attempt
          state { status }
          resourceStates {
            resourceId
            status
            annotation
            resource {
              name
              provider
              fullCloudResourceId
            }
          }
        }
      }
    }
    pageInfo {
      count
    }
  }
}
"""

queries = {
    "1": query1,
    "2": query2,
    "3": query3
}

print("\nSelect a query to run:")
print(" 1 -> List of CONNECTION_LOST Servers")
print(" 2 -> Upcoming Events for specific Month (incomingEvents)")
print(" 3 -> Patching Report for the specific Month & Year (events)")
selected_query = input("Enter the query number (1-3): ").strip()

if selected_query not in queries:
    print("Invalid query selection. Exiting.")
    exit(1)

if selected_query in ["2", "3"]:
    report_year_input = input("Enter the report year (e.g., 2025): ").strip()
    report_month_input = input("Enter the report month (1-12): ").strip()
    try:
        report_year = int(report_year_input)
        report_month = int(report_month_input)
        if not (1 <= report_month <= 12):
            raise ValueError
    except Exception:
        print("Invalid input for month or year. Exiting.")
        exit(1)

all_rows = []

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ist_zone = ZoneInfo("Asia/Kolkata")
API_URL = "https://api.fleetcontrol.nordcloudapp.com/graphql"

customer_keys = list(customers.keys()) if selected == "0" else [selected]

for cust_id in customer_keys:
    info = customers[cust_id]
    CUSTOMER = info["CUSTOMER"]
    CUSTOMER_ID = info["CUSTOMER_ID"]
    API_KEY = info["API_KEY"]
    print(f"\n---- Processing {CUSTOMER} ----")

    HEADERS = {
        "Content-Type": "application/json",
        "X-Api-Key":    API_KEY,
        "X-Customer-ID": CUSTOMER_ID,
        "Accept":       "application/json"
    }
    QUERY = queries[selected_query]

    response = requests.post(API_URL, headers=HEADERS, json={"query": QUERY})
    if response.status_code != 200:
        print(f"[{CUSTOMER}] HTTP {response.status_code} error: {response.text}")
        continue

    data = response.json()
    if data.get("data") is None:
        print(f"[{CUSTOMER}] No data returned. Full response:\n{data}")
        continue

    if selected_query == "1":
        groups = data["data"].get("groups", {}).get("result", [])
        for group in groups:
            gname = group.get("name", "")
            for sel in group.get("resourceSelectors", []):
                res = sel.get("resource")
                if not res: continue
                if res.get("state", {}).get("status") == "CONNECTION_LOST":
                    all_rows.append({
                        "Customer": CUSTOMER,
                        "Resource Group": gname,
                        "Resource Name": res.get("name", ""),
                        "Status": "CONNECTION_LOST"
                    })

    elif selected_query == "2":
        events = data["data"].get("incomingEvents", {}).get("result", [])
        for ev in events:
            st = ev.get("startTime")
            if not st: continue
            try:
                dt = datetime.fromisoformat(st)
            except:
                continue
            tz = ev.get("scheduleTimezone", "UTC")
            try:
                src = ZoneInfo(tz)
            except:
                src = ZoneInfo("UTC")
            dt_ist = dt.astimezone(src).astimezone(ist_zone)
            if dt_ist.year == report_year and dt_ist.month == report_month:
                patch_count = 0
                for action in ev.get("plan", {}).get("planActions", []):
                    if action.get("name", "").lower() == "patch":
                        patch_count = sum(rg.get("totalNumberOfResources", 0)
                                           for rg in action.get("resourceGroups", []))
                        break
                all_rows.append({
                    "Customer": CUSTOMER,
                    "Plan Name": ev.get("name", "Unnamed Plan"),
                    "Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                    "Timezone": tz,
                    "Resource Count": patch_count
                })

    else:  # selected_query == "3"
        events = data["data"].get("events", {}).get("result", [])
        for ev in events:
            st = ev.get("startTime")
            if not st: continue
            try:
                dt_ist = datetime.fromisoformat(st).astimezone(ist_zone)
            except:
                continue
            if dt_ist.year == report_year and dt_ist.month == report_month:
                for action in ev.get("actions", []):
                    if action.get("actionName", "").lower() == "patch":
                        for att in action.get("attempts", []):
                            for rs in att.get("resourceStates", []):
                                res = rs.get("resource") or {}
                                all_rows.append({
                                    "Customer": CUSTOMER,
                                    "Event Name": ev.get("name", ""),
                                    "Event Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                                    "ActionName": action.get("actionName", ""),
                                    "ResourceName": res.get("name", ""),
                                    "ResourceStatus": rs.get("status", ""),
                                    "Annotation": rs.get("annotation", ""),
                                    "Provider": res.get("provider", ""),
                                    "FullResourceID": res.get("fullCloudResourceId", "")
                                })

# Write output
if not all_rows:
    print("\nNo data found for the selected query.")
    exit(0)

if selected_query == "1":
    fieldnames = ["Customer", "Resource Group", "Resource Name", "Status"]
elif selected_query == "2":
    fieldnames = ["Customer", "Plan Name", "Start Time (IST)", "Timezone", "Resource Count"]
else:
    fieldnames = [
        "Customer", "Event Name", "Event Start Time (IST)", "ActionName",
        "ResourceName", "ResourceStatus", "Annotation", "Provider", "FullResourceID"
    ]

# Determine filename
if selected_query == "1":
    csv_filename = ("ALL_CUSTOMERS_connection_lost.csv"
                    if selected == "0" else f"{customers[selected]['CUSTOMER']}_connection_lost.csv")
elif selected_query == "2":
    m = calendar.month_abbr[report_month].lower()
    csv_filename = (f"ALL_CUSTOMERS_incoming_events_{report_year}_{m}.csv"
                    if selected == "0" else f"{customers[selected]['CUSTOMER']}_incoming_events_{report_year}_{m}.csv")
else:
    m = calendar.month_abbr[report_month].lower()
    csv_filename = (f"ALL_CUSTOMERS_events_{report_year}_{m}_patch.csv"
                    if selected == "0" else f"{customers[selected]['CUSTOMER']}_events_{report_year}_{m}_patch.csv")

with open(csv_filename, "w", newline="") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"\nCSV file '{csv_filename}' created with {len(all_rows)} rows.")
