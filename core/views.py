import json
import os
import threading
import urllib.error
import urllib.request

from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


ORDERS = {}
NEXT_ORDER_ID = 1
STORE_LOCK = threading.Lock()


def index(request):
    return render(request, "index.html")


def build_prompt(order_data):
    return f"""
You are a clinical pharmacist writing a concise care plan for internal pharmacy staff.

Create a care plan using these sections exactly:
1. Problem list / Drug therapy problems (DTPs)
2. Goals (SMART)
3. Pharmacist interventions / plan
4. Monitoring plan & lab schedule

Patient first name: {order_data.get("patient_first_name", "")}
Patient last name: {order_data.get("patient_last_name", "")}
Referring provider: {order_data.get("referring_provider", "")}
Referring provider NPI: {order_data.get("referring_provider_npi", "")}
Patient MRN: {order_data.get("patient_mrn", "")}
Primary diagnosis: {order_data.get("patient_primary_diagnosis", "")}
Medication name: {order_data.get("medication_name", "")}
Additional diagnoses: {order_data.get("additional_diagnosis", "")}
Medication history: {order_data.get("medication_history", "")}
Patient records: {order_data.get("patient_records", "")}

Keep the output practical, readable, and ready to show on screen.
""".strip()


def generate_demo_care_plan(order_data):
    medication = order_data.get("medication_name", "the medication")
    diagnosis = order_data.get("patient_primary_diagnosis", "the listed diagnosis")
    patient_name = (
        f'{order_data.get("patient_first_name", "").strip()} '
        f'{order_data.get("patient_last_name", "").strip()}'
    ).strip() or "This patient"

    return f"""Demo care plan

Problem list / Drug therapy problems (DTPs)
- {diagnosis} requires ongoing medication management.
- {medication} should be reviewed for effectiveness and tolerability.
- Patient education and follow-up are needed to support adherence.

Goals (SMART)
- Improve or stabilize symptoms related to {diagnosis} over the next 2 to 4 weeks.
- Confirm that {patient_name} can follow the medication plan as written.
- Monitor for side effects and adjust therapy if clinically needed.

Pharmacist interventions / plan
- Start or continue {medication} as ordered.
- Review administration instructions, expected benefits, and common adverse effects.
- Reinforce adherence and coordinate with the referring provider as needed.

Monitoring plan & lab schedule
- Reassess clinical response at the next follow-up.
- Review side effects, adherence, and any treatment barriers.
- Obtain relevant labs or vitals based on medication and diagnosis.
"""


def call_openai(order_data):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return generate_demo_care_plan(order_data)

    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip()
    payload = {
        "model": model,
        "input": build_prompt(order_data),
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        return generate_demo_care_plan(order_data)

    text = response_data.get("output_text", "").strip()
    if text:
        return text

    return generate_demo_care_plan(order_data)


@csrf_exempt
def create_order(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    global NEXT_ORDER_ID

    payload = json.loads(request.body.decode("utf-8"))
    care_plan = call_openai(payload)

    with STORE_LOCK:
        order_id = NEXT_ORDER_ID
        NEXT_ORDER_ID += 1
        ORDERS[order_id] = {
            "id": order_id,
            "patient_first_name": payload.get("patient_first_name", ""),
            "patient_last_name": payload.get("patient_last_name", ""),
            "referring_provider": payload.get("referring_provider", ""),
            "referring_provider_npi": payload.get("referring_provider_npi", ""),
            "patient_mrn": payload.get("patient_mrn", ""),
            "patient_primary_diagnosis": payload.get("patient_primary_diagnosis", ""),
            "medication_name": payload.get("medication_name", ""),
            "additional_diagnosis": payload.get("additional_diagnosis", ""),
            "medication_history": payload.get("medication_history", ""),
            "patient_records": payload.get("patient_records", ""),
            "care_plan": care_plan,
        }

    return JsonResponse(
        {
            "message": f"好了！订单号是 {order_id}",
            "order_id": order_id,
            "care_plan": care_plan,
        }
    )


def get_order(request, order_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    order = ORDERS.get(order_id)
    if not order:
        return JsonResponse(
            {
                "message": f"找不到订单 {order_id}",
            },
            status=404,
        )

    return JsonResponse(
        {
            "message": f"这是订单 {order_id} 的 care plan",
            "order_id": order_id,
            "care_plan": order["care_plan"],
            "order": order,
        }
    )
