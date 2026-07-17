"""Probe Meta WhatsApp Cloud API to report the real number's messaging status.

Checks:
  * phone number display, verified status, quality rating
  * WABA status (status field, whether it can send)
  * whether the app / number is in sandbox / dev mode (only test numbers send)
"""

import json
import os

import requests

from whatsapp_ai_agent.config import get_settings


def main() -> None:
    s = get_settings()
    token = s.meta_access_token
    waba_id = s.meta_waba_id
    phone_id = s.meta_phone_number_id
    base = s.meta_graph_api_base_url.rstrip("/")
    ver = s.meta_graph_api_version
    headers = {"Authorization": f"Bearer {token}"}

    print(f"WABA ID        : {waba_id}")
    print(f"Phone number ID: {phone_id}")
    print(f"API version    : {ver}\n")

    # 1) Phone number detail
    url = f"{base}/{ver}/{phone_id}"
    r = requests.get(url, headers=headers, params={"fields": "display_phone_number,verified_name,quality_rating,status,code_verification_status"}, timeout=30)
    print("== Phone number ==")
    print(json.dumps(r.json(), indent=2))

    # 2) WABA detail
    url = f"{base}/{ver}/{waba_id}"
    r = requests.get(url, headers=headers, params={"fields": "name,status,account_review_status,message_template_namespace,on_behalf_of_business_info"}, timeout=30)
    print("\n== WABA ==")
    print(json.dumps(r.json(), indent=2))

    # 3) Can the WABA send? Check business info / is it a test WABA
    # A test/demo WABA has account_mode="SANDBOX" or similar
    url = f"{base}/{ver}/{waba_id}"
    r = requests.get(url, headers=headers, params={"fields": "account_mode,primary_funding_id,owner_business_info"}, timeout=30)
    print("\n== WABA mode ==")
    print(json.dumps(r.json(), indent=2))


if __name__ == "__main__":
    main()
