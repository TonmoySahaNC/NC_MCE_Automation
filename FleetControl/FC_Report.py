#!/usr/bin/env python3
# before running: pip install requests tzdata

import requests
import json
import csv
import os
import calendar
import io
import smtplib
from email.message import EmailMessage
from datetime import datetime

# ────────────────────────────────────────────────────────────────────────────────
# 1.  CUSTOMER MAP
# ────────────────────────────────────────────────────────────────────────────────
customers = {
    "1": {"CUSTOMER": "Brother",  "CUSTOMER_ID": "8292fa9a-abef-4173-a22b-ac2e2c8df4bd", "API_KEY": "APaDot2XZYSZLB7xWFjb2N-ZkItvRYaQcqZ0cKrI"},
    "2": {"CUSTOMER": "Grohe",    "CUSTOMER_ID": "940165de-1711-4053-88d6-23e588cc1593", "API_KEY": "2eBuam9jVQxHl3iPPlv6x0Iz6dHK3dFkUM7igZwB"},
    "3": {"CUSTOMER": "Heineken", "CUSTOMER_ID": "a6cabac5-8168-417b-a4bb-a876c955aa3f", "API_KEY": "6blOYBfWBqcqaGzO87m4GQ7W7NMvZ2gmdXpeqQtm"},
    "4": {"CUSTOMER": "Neste",    "CUSTOMER_ID": "3de03704-e850-4cfa-ba2e-7137ae33689f", "API_KEY": "KvkpXy4oSo0H2kRWCjCFnd0XRFSc_fWQly5z4v6A"},
    "5": {"CUSTOMER": "Sandvik",  "CUSTOMER_ID": "5710c478-2f02-4335-a20a-349823e81f1d", "API_KEY": "5K6o9Ciy5KMekktDdCTULOlowg_fiIvfCLgk9sWN"},
    "6": {"CUSTOMER": "Thames",   "CUSTOMER_ID": "bdbc97ab-add5-4d37-afa6-5ebb7435eb3f", "API_KEY": "DkK-BKFDXD5Lwi4Jcq4irxFnOUBI1Bo4Qv5RF_qy"}
}

# ────────────────────────────────────────────────────────────────────────────────
# 2.  USER PROMPTS
# ────────────────────────────────────────────────────────────────────────────────
print("Select a customer:")
print(" 0 -> All")
for k, v in customers.items():
    print(f" {k} -> {v['CUSTOMER']}")
selected = input("Enter the customer number (0‑6): ").strip()

if selected != "0" and selected not in customers:
    print("Invalid selection. Exiting.")
    exit(1)

print("\nSelect a query:")
print(" 1 -> List of CONNECTION_LOST servers")
print(" 2 -> Upcoming Events for specific month (incomingEvents)")
print(" 3 -> Patching report for a specific month & year (events)")
selected_query = input("Enter the query number (1‑3): ").strip()

if selected_query not in {"1", "2", "3"}:
    print("Invalid query selection. Exiting.")
    exit(1)

if selected_query in {"2", "3"}:
    try:
        report_year  = int(input("Report year (e.g. 2025): "))
        report_month = int(input("Report month (1‑12): "))
        if not 1 <= report_month <= 12:
            raise ValueError
    except ValueError:
        print("Invalid month/year input. Exiting.")
        exit(1)

# ────────────────────────────────────────────────────────────────────────────────
# 3.  GRAPHQL QUERIES
# ────────────────────────────────────────────────────────────────────────────────
query1 = """query { groups { result { name resourceSelectors { resource { name state { status } } } } } }"""

query2 = """
query {
  incomingEvents (limit: 500
    filter: { filterBy: { field: START_TIME operator: GT values: "2025-01-01T00:00:00"} }
  ) {
    result { name startTime scheduleTimezone
      plan { planActions { name, resourceGroups { totalNumberOfResources } } }
      estimatedEndTime status
    }
  }
}"""

query3 = """
query {
  events (limit: 500
    filter: { filterBy: { field: START_TIME operator: GT values: "2025-02-01T00:00:00"} }
  ) {
    result {
      name startTime status
      actions {
        actionName type
        attempts {
          resourceStates {
            resourceId status annotation
            resource { name provider fullCloudResourceId }
          }
        }
      }
    }
  }
}"""

queries = {"1": query1, "2": query2, "3": query3}

# ────────────────────────────────────────────────────────────────────────────────
# 4.  TIMEZONE & CONSTANTS
# ────────────────────────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo

ist_zone = ZoneInfo("Asia/Kolkata")
API_URL  = "https://api.fleetcontrol.nordcloudapp.com/graphql"

# ────────────────────────────────────────────────────────────────────────────────
# 5.  DATA COLLECTION
# ────────────────────────────────────────────────────────────────────────────────
all_rows = []
customer_keys = list(customers.keys()) if selected == "0" else [selected]

for cust_id in customer_keys:
    info = customers[cust_id]
    print(f"\n── Processing {info['CUSTOMER']} ──────")

    headers = {
        "Content-Type":  "application/json",
        "X-Api-Key":     info["API_KEY"],
        "X-Customer-ID": info["CUSTOMER_ID"],
        "Accept":        "application/json"
    }

    resp = requests.post(API_URL, headers=headers, json={"query": queries[selected_query]})
    if resp.status_code != 200:
        print(f"[{info['CUSTOMER']}] HTTP {resp.status_code}: {resp.text}")
        continue

    data = resp.json().get("data", {})

    # ─ Query‑specific parsing ─
    if selected_query == "1":
        for grp in data.get("groups", {}).get("result", []):
            for sel in grp.get("resourceSelectors", []):
                res = sel.get("resource") or {}
                if res.get("state", {}).get("status") == "CONNECTION_LOST":
                    all_rows.append({
                        "Customer":       info["CUSTOMER"],
                        "Resource Group": grp.get("name", ""),
                        "Resource Name":  res.get("name", ""),
                        "Status":         "CONNECTION_LOST"
                    })

    elif selected_query == "2":
        for ev in data.get("incomingEvents", {}).get("result", []):
            dt = datetime.fromisoformat(ev["startTime"])
            dt_ist = dt.astimezone(ist_zone)
            if dt_ist.year == report_year and dt_ist.month == report_month:
                patch_cnt = 0
                for act in ev.get("plan", {}).get("planActions", []):
                    if act.get("name", "").lower() == "patch":
                        patch_cnt = sum(rg.get("totalNumberOfResources", 0)
                                        for rg in act.get("resourceGroups", []))
                        break
                all_rows.append({
                    "Customer":        info["CUSTOMER"],
                    "Plan Name":       ev.get("name"),
                    "Start Time (IST)": dt_ist.strftime("%Y‑%m‑%d %H:%M:%S"),
                    "Timezone":        ev.get("scheduleTimezone", "UTC"),
                    "Resource Count":  patch_cnt
                })

    elif selected_query == "3":
        for ev in data.get("events", {}).get("result", []):
            ev_dt = datetime.fromisoformat(ev["startTime"]).astimezone(ist_zone)
            if ev_dt.year == report_year and ev_dt.month == report_month:
                for act in ev["actions"]:
                    if act["actionName"].lower() != "patch":
                        continue
                    for rs in act["attempts"][0]["resourceStates"]:
                        res = rs["resource"] or {}
                        all_rows.append({
                            "Customer":               info["CUSTOMER"],
                            "Event Name":             ev["name"],
                            "Event Start (IST)":      ev_dt.strftime("%Y‑%m‑%d %H:%M:%S"),
                            "ActionName":             act["actionName"],
                            "ResourceName":           res.get("name"),
                            "ResourceStatus":         rs.get("status"),
                            "Annotation":             rs.get("annotation"),
                            "Provider":               res.get("provider"),
                            "FullResourceID":         res.get("fullCloudResourceId")
                        })

# ────────────────────────────────────────────────────────────────────────────────
# 6.  NO DATA → EXIT
# ────────────────────────────────────────────────────────────────────────────────
if not all_rows:
    print("\nNo data found for the selected query.")
    exit(0)

# ────────────────────────────────────────────────────────────────────────────────
# 7.  CSV HEADER + FILENAME
# ────────────────────────────────────────────────────────────────────────────────
if selected_query == "1":
    fieldnames = ["Customer", "Resource Group", "Resource Name", "Status"]
    csv_filename = ("ALL_CUSTOMERS_" if selected == "0" else f"{customers[selected]['CUSTOMER']}_") + "connection_lost.csv"
elif selected_query == "2":
    fieldnames = ["Customer", "Plan Name", "Start Time (IST)", "Timezone", "Resource Count"]
    mon = calendar.month_abbr[report_month].lower()
    prefix = "ALL_CUSTOMERS_" if selected == "0" else f"{customers[selected]['CUSTOMER']}_"
    csv_filename = f"{prefix}incoming_events_{report_year}_{mon}.csv"
else:
    fieldnames = ["Customer", "Event Name", "Event Start (IST)", "ActionName",
                  "ResourceName", "ResourceStatus", "Annotation", "Provider", "FullResourceID"]
    mon = calendar.month_abbr[report_month].lower()
    prefix = "ALL_CUSTOMERS_" if selected == "0" else f"{customers[selected]['CUSTOMER']}_"
    csv_filename = f"{prefix}events_{report_year}_{mon}_patch.csv"

# ────────────────────────────────────────────────────────────────────────────────
# 8.  BUILD CSV *IN MEMORY*
# ────────────────────────────────────────────────────────────────────────────────
csv_buffer = io.StringIO()
writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
writer.writeheader()
writer.writerows(all_rows)
csv_bytes = csv_buffer.getvalue().encode("utf‑8")

print(f"\nCSV built in memory with {len(all_rows)} rows → {csv_filename}")

# ────────────────────────────────────────────────────────────────────────────────
# 9.  SEND E‑MAIL
# ────────────────────────────────────────────────────────────────────────────────
smtp_host = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT", "465"))
smtp_user = os.getenv("SMTP_USER")
smtp_pass = os.getenv("SMTP_PASS")
email_from = os.getenv("EMAIL_FROM", smtp_user or "")
email_to   = os.getenv("EMAIL_TO")

if not all([smtp_host, smtp_pass, email_from, email_to]):
    print("SMTP / email environment variables are missing. Unable to send email.")
    exit(1)

msg = EmailMessage()
msg["From"] = email_from
msg["To"]   = email_to
msg["Subject"] = f"FleetControl Report – {csv_filename}"
msg.set_content("Hi,\n\nPlease find the FleetControl report attached.\n")

msg.add_attachment(csv_bytes,
                   maintype="text",
                   subtype="csv",
                   filename=csv_filename)

print(f"Connecting to SMTP {smtp_host}:{smtp_port} …")
with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
    smtp.login(smtp_user, smtp_pass)
    smtp.send_message(msg)

print(f"Email sent to {email_to}")
