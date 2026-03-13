from flask import Flask, request, jsonify
import json
import requests
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# ===== External API config =====
API_URL = os.getenv("API_URL", "https://clanarina.pzs.si/ajax_check_odos.php")  # your API endpoint

# ===== SMTP / email config =====
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

FROM_EMAIL = os.getenv("FROM_EMAIL")
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS").split(",") if os.getenv("ADMIN_EMAILS") else []

JOTFORM_EMAIL_FIELD_KEY = os.getenv("JOTFORM_EMAIL_FIELD_KEY")
JOTFORM_NAME_FIELD_KEY = os.getenv("JOTFORM_SURNAME_FIELD_KEY")
JOTFORM_PZS_FIELD_KEY = os.getenv("JOTFORM_PZS_FIELD_KEY")


# Validate config at import time
if not all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, ADMIN_EMAILS]):
    raise RuntimeError(
        "Missing configuration: set SMTP_SERVER, SMTP_PORT, SMTP_USER, "
        "SMTP_PASSWORD, FROM_EMAIL, and ADMIN_EMAILS"
    )

if not all([JOTFORM_EMAIL_FIELD_KEY, JOTFORM_NAME_FIELD_KEY, JOTFORM_PZS_FIELD_KEY]):
    raise RuntimeError(
        "Missing Jotform field keys: set JOTFORM_EMAIL_FIELD_KEY, "
        "JOTFORM_NAME_FIELD_KEY, and JOTFORM_PZS_FIELD_KEY"
    )

def check_membership(card_no: str, surname: str) -> dict:
    """
    Call external API to check membership.
    Adjust method, params/body according to your API.
    """
    params = {
        "st_izkaznice": card_no,
        "enaslov": surname,
    }
    resp = requests.get(API_URL, params=params, timeout=10)  # or POST if needed[web:68][web:74]
    resp.raise_for_status()
    resp_json = resp.json()
    if resp_json["result"] == 0:
        return "not a member"
    return "valid membership" if resp_json["valid_membership"] else "invalid membership"

def send_email(subject: str, body: str, to_addrs: list[str]):
    """
    Send a plain‑text email to one or more recipients using SMTP.
    """
    print(f"Preparing email to: {to_addrs}")
    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    print("attaching email body")
    msg.attach(MIMEText(body, "plain"))
    context = ssl.create_default_context()

    print("Initing server connection")
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=10) as server:
        print("Logging in to mail server...")
        server.login(SMTP_USER, SMTP_PASSWORD)
        print("Sending email...")
        server.sendmail(FROM_EMAIL, to_addrs, msg.as_string())

@app.route("/jotform-webhook", methods=["POST"])
def jotform_webhook():
    # Jotform sends multipart/form-data, so fields are in request.form
    form_data = request.form.to_dict(flat=True)

    # Jotform usually includes a 'rawRequest' field with JSON of the submission
    raw_request = form_data.get("rawRequest")

    # Log everything so you can inspect it
    print("---- Incoming Jotform webhook ----")
    # print("Headers:", dict(request.headers))
    # print("Raw request:", raw_request)

    if not raw_request:
        print("No raw request found")
        return jsonify({"status": "error", "message": "No raw request found"}), 400

    # You can parse raw_request if it's JSON to get more structured data
    try:
        raw_request = json.loads(raw_request)
    except json.JSONDecodeError:
        print("Failed to parse raw request as JSON")
        return jsonify({"status": "error", "message": "Invalid raw request format"}), 400

    # Example: access email field directly if you know its key
    # (e.g. 'q3_email' or similar – you will see the exact key in the print above)
    email = raw_request[JOTFORM_EMAIL_FIELD_KEY]
    surname = raw_request[JOTFORM_NAME_FIELD_KEY]['last']
    pzs = raw_request[JOTFORM_PZS_FIELD_KEY]

    if not email:
        print("Email field is missing in the submission, check env JOTFORM_EMAIL_FIELD_KEY")
        return jsonify({"status": "error", "message": "Email field is missing"}), 400
    if not surname:
        print("Surname field is missing in the submission, check env JOTFORM_NAME_FIELD_KEY")
        return jsonify({"status": "error", "message": "Surname field is missing"}), 400
    if not pzs:
        print("PZS field is missing in the submission, check env JOTFORM_PZS_FIELD_KEY")
        return jsonify({"status": "error", "message": "PZS field is missing"}), 400

    # Call your membership API
    try:
        membership_status = check_membership(card_no=pzs, surname=surname)
    except Exception as e:
        print("Error checking membership:", e)
        return jsonify({"status": "error", "message": "Failed to check membership"}), 500

    # Send email to admins with the result
    subject = f"Mladinci PD Vipava: Preverjanje validnosti članarine"
    regards = "Email je avtomatsko generiran, zato nanj ne potrebujete odgovarjati.\nLep pozdrav,\nEkipa mladincev PD Vipava"
    info = "Članarino lahko podaljšate na https://clanarina.pzs.si/"

    if membership_status == "valid membership":
        body = f"Pozdravljeni\n\nPreverili smo članarino za {surname} (PZS: {pzs}) in ugotovili, da je članarina veljavna.\n\n{regards}"
    elif membership_status == "invalid membership":
        body = f"Pozdravljeni\n\nPreverili smo članarino za {surname} (PZS: {pzs}) in ugotovili, da članarina ni veljavna. Kot veste, je pogoj za udeležbo na planinskem taboru članstvo PZS. Prosimo, da se čim prej uredite članarino, da boste lahko sodelovali na taboru.\n\n{info}\n\n{regards}"
    else:
        body = f"Pozdravljeni\n\nPreverili smo članarino za {surname} (PZS: {pzs}) in ugotovili, da ni član PZS. Kot veste, je pogoj za udeležbo na planinskem taboru članstvo PZS. Prosimo, da se čim prej uredite članarino, da boste lahko sodelovali na taboru.\n\n{info}\n\n{regards}"



    try:
        send_email(subject, body, ADMIN_EMAILS)
    except Exception as e:
        print("Error sending email:", e)
        return jsonify({"status": "error", "message": "Failed to send email"}), 500


    # Respond to Jotform
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    # if not all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, ADMIN_EMAILS]):
    #     print("Error: Missing configuration in environment variables")
    #     print("Please set SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, and ADMIN_EMAILS")
    #     exit(1)
    # if not all([JOTFORM_EMAIL_FIELD_KEY, JOTFORM_NAME_FIELD_KEY, JOTFORM_PZS_FIELD_KEY]):
    #     print("Error: Missing Jotform field keys in environment variables")
    #     print("Please set JOTFORM_EMAIL_FIELD_KEY, JOTFORM_NAME_FIELD_KEY, and JOTFORM_PZS_FIELD_KEY")
    #     exit(1)

    # app.run(host="0.0.0.0", port=5412, debug=True)