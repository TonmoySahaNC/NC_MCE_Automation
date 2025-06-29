# before running this script, install required modules:
# pip install requests tzdata

import requests
import json
import csv
import os
import calendar
from datetime import datetime

customers = {
    "1": {"CUSTOMER": "Brother","CUSTOMER_ID": "8292fa9a-abef-4173-a22b-ac2e2c8df4bd","API_KEY": "APaDot2XZYSZLB7xWFjb2N-ZkItvRYaQcqZ0cKrI"},
    "2": {"CUSTOMER": "Grohe","CUSTOMER_ID": "940165de-1711-4053-88d6-23e588cc1593","API_KEY": "2eBuam9jVQxHl3iPPlv6x0Iz6dHK3dFkUM7igZwB"},
    "3": {"CUSTOMER": "Heineken","CUSTOMER_ID": "a6cabac5-8168-417b-a4bb-a876c955aa3f","API_KEY": "6blOYBfWBqcqaGzO87m4GQ7W7NMvZ2gmdXpeqQtm"},
    "4": {"CUSTOMER": "Neste","CUSTOMER_ID": "3de03704-e850-4cfa-ba2e-7137ae33689f","API_KEY": "KvkpXy4oSo0H2kRWCjCFnd0XRFSc_fWQly5z4v6A"},
    "5": {"CUSTOMER": "Sandvik","CUSTOMER_ID": "5710c478-2f02-4335-a20a-349823e81f1d","API_KEY": "5K6o9Ciy5KMekktDdCTULOlowg_fiIvfCLgk9sWN"},
    "6": {"CUSTOMER": "Thames","CUSTOMER_ID": "bdbc97ab-add5-4d37-afa6-5ebb7435eb3f","API_KEY": "DkK-BKFDXD5Lwi4Jcq4irxFnOUBI1Bo4Qv5RF_qy"}
}
print("Select a customer by entering the corresponding number:")
print(" 0 -> All")
print(" 1 -> Brother")
print(" 2 -> Grohe")
print(" 3 -> Heineken")
print(" 4 -> Neste")
print(" 5 -> Sandvik")
print(" 6 -> Thames Water")
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
    cust_info = customers[cust_id]
    CUSTOMER   = cust_info["CUSTOMER"]
    CUSTOMER_ID = cust_info["CUSTOMER_ID"]
    API_KEY     = cust_info["API_KEY"]
    print(f"\n---- Processing {CUSTOMER} ----")

    HEADERS = {
        "Content-Type": "application/json",
        "X-Api-Key":    API_KEY,
        "X-Customer-ID": CUSTOMER_ID,
        "Accept":       "application/json"
    }
    QUERY = queries[selected_query]

    # Send POST
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
            group_name = group.get("name", "")
            for selector in group.get("resourceSelectors", []):
                resource = selector.get("resource")
                if not resource:
                    continue
                status = resource.get("state", {}).get("status", "")
                if status == "CONNECTION_LOST":
                    resource_name = resource.get("name", "")
                    row = {
                        "Customer":      CUSTOMER,
                        "Resource Group": group_name,
                        "Resource Name":  resource_name,
                        "Status":         status
                    }
                    all_rows.append(row)


    elif selected_query == "2":
        events = data["data"].get("incomingEvents", {}).get("result", [])
        for event in events:
            start_time_str = event.get("startTime")
            if not start_time_str:
                continue
            try:
                dt = datetime.fromisoformat(start_time_str)
            except Exception as e:
                print(f"[{CUSTOMER}] Error parsing startTime '{start_time_str}': {e}")
                continue

            tz_source_name = event.get("scheduleTimezone", "UTC")
            try:
                tz_source = ZoneInfo(tz_source_name)
            except Exception:
                tz_source = ZoneInfo("UTC")

            dt_source = dt.astimezone(tz_source)
            dt_ist    = dt_source.astimezone(ist_zone)
            if dt_ist.year == report_year and dt_ist.month == report_month:
                plan_name = event.get("name", "Unnamed Plan")
                plan      = event.get("plan", {})
                patch_count = 0
                for action in plan.get("planActions", []):
                    if action.get("name", "").lower() == "patch":
                        patch_count = sum(
                            rg.get("totalNumberOfResources", 0)
                            for rg in action.get("resourceGroups", [])
                        )
                        break
                row = {
                    "Customer":        CUSTOMER,
                    "Plan Name":       plan_name,
                    "Start Time (IST)": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
                    "Timezone":        tz_source_name,
                    "Resource Count":  patch_count
                }
                all_rows.append(row)

    elif selected_query == "3":
        events = data["data"].get("events", {}).get("result", [])
        for event in events:
            event_name     = event.get("name", "")
            start_time_str = event.get("startTime", "")
            if not start_time_str:
                continue
            try:
                dt = datetime.fromisoformat(start_time_str)
                dt_ist = dt.astimezone(ist_zone)
                event_start = dt_ist.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"[{CUSTOMER}] Error parsing startTime '{start_time_str}': {e}")
                continue

            if dt_ist.year == report_year and dt_ist.month == report_month:
                for action in event.get("actions", []):
                    if action.get("actionName", "").lower() == "patch":
                        action_name = action.get("actionName", "")
                        for attempt in action.get("attempts", []):
                            for rs in attempt.get("resourceStates", []):
                                resource = rs.get("resource") or {}
                                resource_name   = resource.get("name", "")
                                resource_status = rs.get("status", "")
                                annotation      = rs.get("annotation", "")
                                provider        = resource.get("provider", "")
                                full_id         = resource.get("fullCloudResourceId", "")
                                row = {
                                    "Customer":                CUSTOMER,
                                    "Event Name":              event_name,
                                    "Event Start Time (IST)":  event_start,
                                    "ActionName":              action_name,
                                    "ResourceName":            resource_name,
                                    "ResourceStatus":          resource_status,
                                    "Annotation":              annotation,
                                    "Provider":                provider,
                                    "FullResourceID":          full_id
                                }
                                all_rows.append(row)

if not all_rows:
    print("\nNo data found for the selected query.")
    exit(0)

if selected_query == "1":
    fieldnames  = ["Customer", "Resource Group", "Resource Name", "Status"]
    csv_filename = "ALL_CUSTOMERS_connection_lost.csv" if selected == "0" else f"{customers[selected]['CUSTOMER']}_connection_lost.csv"

elif selected_query == "2":
    fieldnames  = ["Customer", "Plan Name", "Start Time (IST)", "Timezone", "Resource Count"]
    month_abbr  = calendar.month_abbr[report_month].lower()
    if selected == "0":
        csv_filename = f"ALL_CUSTOMERS_incoming_events_{report_year}_{month_abbr}.csv"
    else:
        csv_filename = f"{customers[selected]['CUSTOMER']}_incoming_events_{report_year}_{month_abbr}.csv"

else:
    fieldnames = [
        "Customer",
        "Event Name",
        "Event Start Time (IST)",
        "ActionName",
        "ResourceName",
        "ResourceStatus",
        "Annotation",
        "Provider",
        "FullResourceID"
    ]
    month_abbr = calendar.month_abbr[report_month].lower()
    if selected == "0":
        csv_filename = f"ALL_CUSTOMERS_events_{report_year}_{month_abbr}_patch.csv"
    else:
        csv_filename = f"{customers[selected]['CUSTOMER']}_events_{report_year}_{month_abbr}_patch.csv"


with open(csv_filename, "w", newline="") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"\nCSV file '{csv_filename}' created with {len(all_rows)} rows.")

if selected_query == "3":
    total_resources = len(all_rows)
    status_counts = {}
    for row in all_rows:
        stat = row.get("ResourceStatus", "")
        status_counts[stat] = status_counts.get(stat, 0) + 1

    print(f"\nTotal resources in this report: {total_resources}")
    for stat, count in status_counts.items():
        print(f"Count of ResourceStatus '{stat}': {count}")

if os.path.exists("output.json"):
    os.remove("output.json")
