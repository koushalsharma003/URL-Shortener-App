from flask import Flask, request, redirect, jsonify, abort
import random
import string
import time
import uuid
import os
from datetime import datetime, timedelta, timezone
import logging
import json
from urllib.parse import urlparse
import threading
from collections import deque

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SHORT_DOMAIN = os.getenv("SHORT_DOMAIN", "http://localhost:5000/")

# For generating short codes
SHORT_CODE_LENGTH = 7
SHORT_CODE_CHARS = string.ascii_letters + string.digits

# Analytics settings
LAST_N_ACCESSES = 100 # Store last 100 accesses for each short URL

# Rate limiting settings (per IP)
RATE_LIMIT_ENABLED = True
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", 100)) # Max requests
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", 3600)) # Per hour (3600 seconds)


ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "supersecretadminkey") # CHANGE THIS IN PRODUCTION!

url_store = {}
url_store_lock = threading.Lock()


rate_limit_store = {}
rate_limit_lock = threading.Lock()

def generate_short_code():
    """Generates a unique short code."""
    with url_store_lock:
        while True:
            code = ''.join(random.choices(SHORT_CODE_CHARS, k=SHORT_CODE_LENGTH))
            if code not in url_store:
                return code

def is_valid_url(url_string):
    """Basic validation for a URL."""
    try:
        result = urlparse(url_string)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except ValueError:
        return False

def record_access_event(short_code, ip_address, user_agent, referrer):
    """Records an access event for analytics."""
    with url_store_lock:
        if short_code not in url_store:
            logging.warning(f"Attempted to record access for non-existent short code: {short_code}")
            return

        entry = url_store[short_code]
        analytics = entry["analytics"]
        
        analytics["total_clicks"] += 1
        access_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip": ip_address,
            "userAgent": user_agent,
            "referrer": referrer,
        }
        analytics["recent_accesses"].append(access_info)
        logging.info(f"Recorded click for short code '{short_code}' from IP {ip_address}")


def check_rate_limit(ip_address):
    """Checks and updates the rate limit for a given IP address."""
    if not RATE_LIMIT_ENABLED:
        return True

    with rate_limit_lock:
        current_time = datetime.now(timezone.utc)
        
        if ip_address in rate_limit_store:
            rate_limit_store[ip_address] = [
                t for t in rate_limit_store[ip_address] 
                if current_time - t < timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
            ]
        else:
            rate_limit_store[ip_address] = []

        if len(rate_limit_store[ip_address]) >= RATE_LIMIT_MAX_REQUESTS:
            return False
        
        rate_limit_store[ip_address].append(current_time)
        return True


@app.route("/api/shorten", methods=["POST"])
def shorten_url():
    """Handles requests to shorten a URL."""
    client_ip = request.remote_addr

    if not check_rate_limit(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429 

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    long_url = data.get("longUrl")
    custom_alias = data.get("customAlias")
    expiry_date_str = data.get("expiryDate")

    if not long_url:
        return jsonify({"error": "longUrl is required"}), 400

    if not is_valid_url(long_url):
        return jsonify({"error": "Invalid URL format."}), 400

    short_code = custom_alias
    if not short_code:
        short_code = generate_short_code()

    expires_at = None
    if expiry_date_str:
        try:
            expires_at = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({"error": "Invalid expiry date format. Use YYYY-MM-DDTHH:MM:SSZ (ISO 8601)."}), 400

    with url_store_lock:
        if short_code in url_store:
            return jsonify({"error": f"Custom alias '{custom_alias}' already exists."}), 409

        url_store[short_code] = {
            "mapping": {
                "shortCode": short_code,
                "longUrl": long_url,
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "expiresAt": expires_at.isoformat() if expires_at else None,
                "userId": None
            },
            "analytics": {
                "total_clicks": 0,
                "recent_accesses": deque(maxlen=LAST_N_ACCESSES)
            }
        }

    response_data = {
        "shortUrl": f"{SHORT_DOMAIN}{short_code}",
        "longUrl": long_url,
        "shortCode": short_code
    }

    logging.info(f"Shortened URL: {long_url} -> {response_data['shortUrl']}")
    return jsonify(response_data), 201

@app.route("/<short_code>", methods=["GET"])
def redirect_url(short_code):
    """Handles redirection from a short URL to the original long URL."""
    with url_store_lock:
        entry = url_store.get(short_code)

    if not entry:
        abort(404, description="Short URL does not exist.")

    mapping = entry["mapping"]

    if mapping["expiresAt"]:
        expires_at = datetime.fromisoformat(mapping["expiresAt"])
        if datetime.now(timezone.utc) > expires_at:
            with url_store_lock:
                if short_code in url_store: 
                    del url_store[short_code]
            abort(404, description="Short URL has expired.")


    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    referrer = request.headers.get("Referer")
    threading.Thread(target=record_access_event, args=(short_code, client_ip, user_agent, referrer)).start()

    logging.info(f"Redirecting {short_code} to {mapping['longUrl']}")
    return redirect(mapping["longUrl"], code=302)

@app.route("/api/analytics/<short_code>", methods=["GET"])
def get_analytics(short_code):
    """Returns analytics for a given short URL."""
    with url_store_lock:
        entry = url_store.get(short_code)

    if not entry:
        return jsonify({"error": f"Short code '{short_code}' not found or no analytics available."}), 404

    mapping = entry["mapping"]
    analytics = entry["analytics"]

    response_data = {
        "shortCode": short_code,
        "longUrl": mapping["longUrl"],
        "totalClicks": analytics["total_clicks"],
        "recentClicks": list(analytics["recent_accesses"])
    }
    return jsonify(response_data), 200

@app.route("/api/admin/shorten/<short_code>", methods=["DELETE"])
def delete_short_url(short_code):
    """Deletes a short URL (admin access required)."""
    auth_header = request.headers.get("X-Admin-API-Key")
    if not auth_header or auth_header != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    with url_store_lock:
        if short_code in url_store:
            del url_store[short_code]
            logging.info(f"Admin deleted short code: {short_code}")
            return jsonify({"message": f"Short URL '{short_code}' deleted successfully."}), 200
        else:
            return jsonify({"error": f"Short code '{short_code}' not found."}), 404

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logging.info(f"Server starting on port {port}...")
    logging.info(f"Rate Limiting Enabled: {RATE_LIMIT_ENABLED}")
    if RATE_LIMIT_ENABLED:
        logging.info(f"Rate Limit: {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds")
    logging.info(f"Admin API Key: {ADMIN_API_KEY[:4]}... (first 4 chars)") # Avoid logging full key


    app.run(host="0.0.0.0", port=port, debug=False) 
