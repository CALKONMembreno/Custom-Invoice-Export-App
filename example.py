import requests
import json
import csv
from datetime import datetime


def iso_datetime_to_date(value):
    """Return YYYY-MM-DD from ISO timestamps like 2024-03-15T13:55:07Z."""
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    # Fast path: ISO 8601 values start with the date.
    if len(text) >= 10:
        return text[:10]
    return text

#Starts authentication process
# Ensure you have a file named 'api_secrets.json' with the required keys

# Load API credentials from the 'api_secrets.json' file. This file should contain the necessary keys for authentication:
# - entityRef: The entity reference for the API
# - apiKey: The API key for authentication
# - clientId: The client ID for OAuth
# - clientSecret: The client secret for OAuth
# - apiScopeRef: The API scope reference

with open('api_secrets.json', 'r') as f:
    api_secrets = json.load(f)

entity_ref = api_secrets.get("entityRef")
apikey = api_secrets.get("apiKey")
client_id = api_secrets.get("clientId")
client_secret= api_secrets.get("clientSecret")
api_scope = api_secrets.get("apiScopeRef")

headers = {
    "accept": "application/json",
    "x-api-key": apikey,
    "Content-Type": "application/json"
}

payload = {
    "clientId": client_id,
    "clientSecret": client_secret,
    "apiScopeRef":  api_scope
}

auth_url = f"https://api.us.commandalkon.io/v4/services/authnz/{entity_ref}/api/login"


def _safe_json(response: requests.Response):
    if not response.content:
        return {}
    try:
        return response.json()
    except Exception:
        return {"_raw": response.text}


def login_get_refresh_token() -> str:
    auth = requests.post(auth_url, json=payload, headers=headers, timeout=30)
    if auth.status_code != 200:
        print("Failed to authenticate. Check your credentials and API secrets.")
        print(f"Auth status: {auth.status_code}")
        print(json.dumps(_safe_json(auth), indent=2))
        raise RuntimeError("Authentication failed")

    refresh_token = _safe_json(auth).get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh_token found in login response")
    return refresh_token


def refresh_access_token(refresh_token: str) -> str:
    refresh_headers = dict(headers)
    refresh_headers["authorization"] = f"Bearer {refresh_token}"

    refresh_url = (
        f"https://api.us.commandalkon.io/v4/services/authnz/{entity_ref}/api/tokens/refresh-access-token"
    )

    refreshed = requests.get(refresh_url, headers=refresh_headers, timeout=30)
    if refreshed.status_code != 200:
        print("Failed to refresh access token.")
        print(f"Refresh status: {refreshed.status_code}")
        print(json.dumps(_safe_json(refreshed), indent=2))
        raise RuntimeError("Access token refresh failed")

    access_token = _safe_json(refreshed).get("access_token")
    if not access_token:
        raise RuntimeError("No access_token found in refresh response")
    return access_token


def ensure_access_token():
    global refresh_token
    global access_token

    if not refresh_token:
        refresh_token = login_get_refresh_token()
    access_token = refresh_access_token(refresh_token)
    headers["authorization"] = f"Bearer {access_token}"


def request_with_token_refresh(method: str, url: str, *, json_payload=None, params=None, timeout=15):
    """Makes a request; if it returns 401, refresh token and retry once."""
    response = requests.request(method, url, headers=headers, json=json_payload, params=params, timeout=timeout)
    if response.status_code != 401:
        return response

    print("Received 401; refreshing access token and retrying once...")
    try:
        ensure_access_token()
    except Exception:
        # If refresh fails (e.g., refresh token expired), try a full login once.
        print("Token refresh failed; re-authenticating and retrying once...")
        refresh_token_local = login_get_refresh_token()
        access_token_local = refresh_access_token(refresh_token_local)
        globals()["refresh_token"] = refresh_token_local
        globals()["access_token"] = access_token_local
        headers["authorization"] = f"Bearer {access_token_local}"

    return requests.request(method, url, headers=headers, json=json_payload, params=params, timeout=timeout)


refresh_token = ""
access_token = ""
ensure_access_token()

# Function to update item details
# When using this script, change file name and payload as needed

####IMPORTANT: Make sure to change the filename and payload according to your needs####
#This is the file that contains the data to update, it should have a column named 'Internal Mix Design ID' with the CRN values
filename = 'customers-penny-deleted.csv'

def get_projects():
    url = f"https://api.us.commandalkon.io/v4/services/setup/{entity_ref}/projects/paginated"

    projects_list = []
    page_token = None
    seen_tokens = set()
    page_num = 0

    while True:
        params = {}
        if page_token:
            # Prevent accidental infinite loops if the API returns a repeated token.
            if page_token in seen_tokens:
                print("Pagination stopped: repeating pageToken detected.")
                break
            seen_tokens.add(page_token)
            params["pageToken"] = page_token
        
        params["activeOnly"] = "false"
        response = request_with_token_refresh("GET", url, params=params, timeout=30)
        response_data = _safe_json(response)

        if response.status_code != 200:
            print(f"Error fetching projects: {json.dumps(response_data, indent=2)}")
            return []

        page_num += 1

        # The paginated endpoint returns an object (dict) containing a list.
        page_items = []
        if isinstance(response_data, list):
            page_items = response_data
        elif isinstance(response_data, dict):
            for key in ("items", "results", "data", "projects", "content"):
                value = response_data.get(key)
                if isinstance(value, list):
                    page_items = value
                    break

        projects_list.extend(page_items)
        print(f"Fetched page {page_num} ({len(page_items)} items). Total: {len(projects_list)}")

        # When there are no more pages, the token is not present.
        if isinstance(response_data, dict):
            page_token = response_data.get("pageToken") or response_data.get("nextPageToken")
        else:
            page_token = None

        if not page_token:
            break

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    print(f"Fetched {len(projects_list)} projects total.")

    # Flatten and export to CSV
    fieldnames = [
        "crn",
        "createDate",
        "modifyDate",
        "id",
        "name",
        "customer",
        "startDate",
        "endDate",
        "status",
    ]
    flattened_projects = []
    for project in projects_list:
        flattened_projects.append({
            "crn": project.get("crn"),
            "createDate": iso_datetime_to_date(project.get("createDate")),
            "modifyDate": iso_datetime_to_date(project.get("modifyDate")),
            "id": project.get("id"),
            "name": project.get("name"),
            "customer": project.get("customerParty", {}).get("name"),
            "startDate": iso_datetime_to_date(project.get("startDate")),
            "endDate": iso_datetime_to_date(project.get("endDate")),
            "status": project.get("status"),
        })

    csv_filename = f"projects_{timestamp}.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flattened_projects)

    print(f"Projects exported to {csv_filename}")
    return projects_list

def update_item(crn, projects):
    url = f"https://api.us.commandalkon.io/v4/services/setup/{entity_ref}/customers/{crn}"
    
    ###IMPORTANT: Make sure to change the payload according to your needs ###
    #This is the payload that will be sent to the API for mix design updates
    # Prepare the payload with the mix design data based on API specification
    
    # Helper function to convert yes/no to boolean
    def to_boolean(value):
        if value is None or value == '':
            return False
        return str(value).lower() == 'yes'
    
    # Helper function to handle empty values
    def safe_get(value, default=""):
        return value if value is not None and value != '' else default
    
    # Helper function to convert date to ISO 8601 format
    def convert_to_iso_date(date_str):
        if not date_str or date_str.strip() == '':
            return None
        
        try:
            # Parse the date from MM/dd/yyyy format
            date_obj = datetime.strptime(date_str.strip(), '%m/%d/%Y')
            # Convert to ISO 8601 format with timezone (UTC)
            return date_obj.strftime('%Y-%m-%dT00:00:00Z')
        except ValueError as e:
            print(f"Error parsing date '{date_str}': {e}")
            return None
    
    # Build payload dynamically, excluding empty values
    payload = {
          "status": safe_get(projects.get("status"), "DELETED"),
          
        # "purchaseOrderRequiredInOrder": to_boolean(projects.get("purchaseOrderRequired")),
        # "ticketOptions": {
        #     "printPaperTickets": "yes",
        #     "printWeights": "no"
        # },
        # "salesPersonRef": projects.get("salesperson"),
        # "taxStatus": safe_get(projects.get("taxStatus"), "TAXABLE"),
        # "pricingOptions": {
        #     "showPricing": 'no'
        # },
        # "restrictToPriceBook": safe_get(projects.get("restrictToPriceBook").lower(), "primary"),
        # "customerJobRequiredInOrder": to_boolean(projects.get("customerJobRequired"))
    }
    
    # Add optional fields only if they have values
    purchase_order = safe_get(projects.get("purchaseOrder"))
    if purchase_order:
        payload["purchaseOrder"] = purchase_order
    
    postal_code = safe_get(projects.get("postalCode"))
    if postal_code:
        payload["address"] = {"postalCode": postal_code}
    
    cost_book_ref = safe_get(projects.get("priceBookRef"))
    if cost_book_ref:
        payload["costBookRef"] = cost_book_ref
    
    tax_exempt_reason = safe_get(projects.get("taxExemptReasonRef"))
    if tax_exempt_reason:
        payload["taxExemptReasonRef"] = tax_exempt_reason
    
    start_date = convert_to_iso_date(projects.get("startDate"))
    if start_date:
        payload["startDate"] = start_date
    
    end_date = convert_to_iso_date(projects.get("endDate"))
    if end_date:
        payload["endDate"] = end_date
    
    print(f"Updating projects {crn} with payload:")
    print(json.dumps(payload, indent=2))
    
    try:
        response = request_with_token_refresh("PATCH", url, json_payload=payload, timeout=15)
        response_data = _safe_json(response)
        print(f"Response status: {response.status_code}, ID: {crn}")
        
        if response.status_code == 200:
            print(f"Success: {response_data.get('id', 'No ID returned')}")
            return True, None
        else:
            print(f"Error response: {json.dumps(response_data, indent=2)}")
            # Store failed response data for later saving
            failed_response = {
                "timestamp": datetime.now().isoformat(),
                "crn": crn,
                "url": url,
                "payload": payload,
                "status_code": response.status_code,
                "response": response_data
            }
            return False, failed_response
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

last_internal_id = None
success_count = 0
fail_count = 0
failed_responses = []  # List to store failed responses

# Read the CSV file and update each mix design
# Group projects by mix design ID since each row is a project
projects = {}

with open(filename, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    
    print(reader.fieldnames)
    
    for row in reader:
        internal_id = row.get('\ufeffInternal ID')
        
        if internal_id not in projects:
            # Initialize project data with simplified structure based on CSV columns
            projects[internal_id] = {
                "status": row.get('Status (Required for import)'),
                # "purchaseOrder": row.get('Purchase Order Number'),
                # "postalCode": row.get('Postal Code'),
                # "priceBookRef": row.get('price book crn'),
                # "startDate": row.get('Start Date (Required for import)'),
                # "endDate": row.get('End Date (Required for import)'),
                # "taxStatus": row.get('Tax Status (Required for import)'),
                # "taxExemptReasonRef": row.get('Tax Exempt Reason ID (Required for import if Tax Status is EXEMPT)'),
                # "showPricing": row.get('Print/Send Prices to Batch'),
                # "printPaperTickets": row.get('Print paper tickets for this project'),
                # "printWeights": row.get('Print Weights on Tickets'),
                # "customerJobRequired": row.get('Customer Job Number required in Order entry'),
                # "purchaseOrderRequired": row.get('Purchase Order required in Order entry'),
                # "restrictToPriceBook": row.get('Order Restrictions (Required for import)'),
                # "salesperson": row.get('Salesperson')
            }
        


# Update each projects
count = 0
for internal_id, project_data in projects.items():
    last_internal_id = internal_id
    success, info = update_item(
        crn=internal_id, projects=project_data
    )
    
    if success:
        success_count += 1
    else:
        fail_count += 1
        if isinstance(info, dict):  # If info is the failed response dict
            failed_responses.append(info)
            print(f"Update failed for Internal Mix Design ID: {internal_id} (Status: {info.get('status_code')})")
        else:
            print(f"Update failed for Internal Mix Design ID: {internal_id} ({info})")
    
    count += 1
    # if count >= 4:
    #     break  # Remove this break to process all mix designs

print(f"Update complete. Success: {success_count}, Failed: {fail_count}")
print(f"Last crn processed: {last_internal_id}")
print(f"Total crn processed: {count}")

# Save failed responses to a JSON file
if failed_responses:
    failed_responses_filename = f"failed_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(failed_responses_filename, 'w', encoding='utf-8') as f:
        json.dump(failed_responses, f, indent=4, ensure_ascii=False)
    print(f"Failed responses saved to: {failed_responses_filename}")
else:
    print("No failed responses to save.")
print(f"Last Internal crn processed: {last_internal_id}")
print(f"Total crn processed: {count}")

