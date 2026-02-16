"""
IG Tool License Server — Flask API for Vercel
Endpoints:
  POST /api/validate          — App validates license key
  POST /api/activate          — App activates license on machine
  POST /api/trial             — App requests trial license
  GET  /api/health            — Health check
  POST /api/admin/generate    — Admin generates a new key
  GET  /api/admin/keys        — Admin lists all keys
  GET  /api/admin/stats       — Admin dashboard stats
  POST /api/admin/revoke      — Admin revokes a key
  POST /api/admin/extend      — Admin extends a key
  POST /api/admin/delete      — Admin deletes a key
  POST /api/admin/deactivate  — Admin removes a machine from a key
"""

from flask import Flask, request, jsonify, send_from_directory
from upstash_redis import Redis
import os
import json
import uuid
import hashlib
import time
from datetime import datetime

app = Flask(__name__, static_folder='../public', static_url_path='')

# ==================== CONFIG ====================
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

TIERS = {
    "trial": {
        "name": "Trial",
        "max_machines": 1,
        "features": ["home_feed_warmup"],
        "max_profiles": 1,
        "duration_days": 3,
        "price": 0
    },
    "basic": {
        "name": "Basic",
        "max_machines": 1,
        "features": ["home_feed_warmup", "dm_outreach"],
        "max_profiles": 1,
        "duration_days": 30,
        "price": 29
    },
    "pro": {
        "name": "Pro",
        "max_machines": 3,
        "features": [
            "home_feed_warmup", "reels_warmup", "story_warmup",
            "keyword_search", "profile_visit", "dm_outreach",
            "voice_notes"
        ],
        "max_profiles": 3,
        "duration_days": 30,
        "price": 49
    },
    "agency": {
        "name": "Agency",
        "max_machines": 10,
        "features": [
            "home_feed_warmup", "reels_warmup", "story_warmup",
            "keyword_search", "profile_visit", "dm_outreach",
            "voice_notes", "unlimited_profiles"
        ],
        "max_profiles": 999,
        "duration_days": 30,
        "price": 99
    }
}

# ==================== HELPERS ====================

def get_redis():
    """Get Upstash Redis client"""
    return Redis(
        url=os.environ.get("UPSTASH_REDIS_REST_URL", ""),
        token=os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    )


def generate_key():
    """Generate license key: IGTOOL-XXXX-XXXX-XXXX-XXXX"""
    parts = [uuid.uuid4().hex[:4].upper() for _ in range(4)]
    return f"IGTOOL-{'-'.join(parts)}"


def verify_admin(req):
    """Verify admin password from header or body"""
    password = req.headers.get("X-Admin-Password", "")
    if not password:
        data = req.get_json(silent=True) or {}
        password = data.get("admin_password", "")
    return password == ADMIN_PASSWORD


def cors_response(data, status=200):
    """JSON response with CORS headers"""
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Password"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
    return resp


def get_license(redis, key):
    """Fetch and parse license data from Redis"""
    raw = redis.get(f"license:{key}")
    if not raw:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def save_license(redis, key, data):
    """Save license data to Redis"""
    redis.set(f"license:{key}", json.dumps(data))


# ==================== CORS PREFLIGHT ====================

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Password"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
        return resp


# ==================== APP ENDPOINTS ====================

@app.route("/api/validate", methods=["POST", "OPTIONS"])
def validate_license():
    """Validate a license key from the desktop app"""
    data = request.get_json(silent=True)
    if not data:
        return cors_response({"valid": False, "error": "Invalid request"}, 400)

    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()
    if not key or not hwid:
        return cors_response({"valid": False, "error": "Missing key or hwid"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"valid": False, "error": "Invalid license key"})

    if lic.get("revoked"):
        return cors_response({"valid": False, "error": "License has been revoked"})

    expires_at = lic.get("expires_at", 0)
    if time.time() > expires_at:
        return cors_response({"valid": False, "error": "License has expired"})

    machines = lic.get("machines", [])
    if hwid not in [m["hwid"] for m in machines]:
        return cors_response({"valid": False, "error": "Machine not activated"})

    tier = lic.get("tier", "basic")
    tier_info = TIERS.get(tier, TIERS["basic"])

    lic["last_validated"] = time.time()
    save_license(redis, key, lic)

    return cors_response({
        "valid": True,
        "tier": tier,
        "tier_name": tier_info["name"],
        "features": tier_info["features"],
        "max_profiles": tier_info["max_profiles"],
        "expires_at": expires_at,
        "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/activate", methods=["POST", "OPTIONS"])
def activate_license():
    """Activate a license key on a new machine"""
    data = request.get_json(silent=True)
    if not data:
        return cors_response({"success": False, "error": "Invalid request"}, 400)

    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()
    machine_name = data.get("machine_name", "Unknown")
    if not key or not hwid:
        return cors_response({"success": False, "error": "Missing key or hwid"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Invalid license key"})

    if lic.get("revoked"):
        return cors_response({"success": False, "error": "License has been revoked"})

    expires_at = lic.get("expires_at", 0)
    if time.time() > expires_at:
        return cors_response({"success": False, "error": "License has expired"})

    machines = lic.get("machines", [])
    tier = lic.get("tier", "basic")
    tier_info = TIERS.get(tier, TIERS["basic"])
    max_machines = lic.get("max_machines_override") or tier_info["max_machines"]

    # Already activated on this machine
    for m in machines:
        if m["hwid"] == hwid:
            return cors_response({
                "success": True,
                "message": "Machine already activated",
                "tier": tier,
                "tier_name": tier_info["name"],
                "features": tier_info["features"],
                "max_profiles": tier_info["max_profiles"],
                "expires_at": expires_at
            })

    if len(machines) >= max_machines:
        return cors_response({
            "success": False,
            "error": f"Machine limit reached ({max_machines} max). Deactivate a machine first or upgrade your plan."
        })

    machines.append({
        "hwid": hwid,
        "machine_name": machine_name,
        "activated_at": time.time()
    })
    lic["machines"] = machines
    lic["last_validated"] = time.time()
    save_license(redis, key, lic)

    return cors_response({
        "success": True,
        "message": "Machine activated successfully",
        "tier": tier,
        "tier_name": tier_info["name"],
        "features": tier_info["features"],
        "max_profiles": tier_info["max_profiles"],
        "expires_at": expires_at
    })


@app.route("/api/trial", methods=["POST", "OPTIONS"])
def create_trial():
    """Create a free trial license tied to hardware ID"""
    data = request.get_json(silent=True)
    if not data:
        return cors_response({"success": False, "error": "Invalid request"}, 400)

    hwid = data.get("hwid", "").strip()
    machine_name = data.get("machine_name", "Unknown")
    if not hwid:
        return cors_response({"success": False, "error": "Missing hwid"}, 400)

    redis = get_redis()

    # Check if HWID already used a trial
    existing = redis.get(f"trial_hwid:{hwid}")
    if existing:
        return cors_response({"success": False, "error": "Trial already used on this machine. Please purchase a license."})

    key = generate_key()
    tier_info = TIERS["trial"]
    expires_at = time.time() + (tier_info["duration_days"] * 86400)

    lic = {
        "key": key,
        "tier": "trial",
        "created_at": time.time(),
        "expires_at": expires_at,
        "revoked": False,
        "machines": [{
            "hwid": hwid,
            "machine_name": machine_name,
            "activated_at": time.time()
        }],
        "last_validated": time.time(),
        "notes": "Auto-generated trial"
    }

    save_license(redis, key, lic)
    redis.set(f"trial_hwid:{hwid}", key)
    redis.sadd("all_license_keys", key)

    return cors_response({
        "success": True,
        "key": key,
        "tier": "trial",
        "tier_name": tier_info["name"],
        "features": tier_info["features"],
        "max_profiles": tier_info["max_profiles"],
        "expires_at": expires_at,
        "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
    })


# ==================== ADMIN ENDPOINTS ====================

@app.route("/api/admin/generate", methods=["POST", "OPTIONS"])
def admin_generate():
    """Generate a new license key"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    tier = data.get("tier", "basic")
    duration_days = int(data.get("duration_days", 30))
    max_machines = int(data.get("max_machines", 0))
    notes = data.get("notes", "")

    if tier not in TIERS:
        return cors_response({"success": False, "error": f"Invalid tier: {tier}"}, 400)

    tier_info = TIERS[tier]
    if max_machines <= 0:
        max_machines = tier_info["max_machines"]

    key = generate_key()
    expires_at = time.time() + (duration_days * 86400)

    lic = {
        "key": key,
        "tier": tier,
        "created_at": time.time(),
        "expires_at": expires_at,
        "revoked": False,
        "machines": [],
        "max_machines_override": max_machines if max_machines != tier_info["max_machines"] else None,
        "last_validated": None,
        "notes": notes
    }

    redis = get_redis()
    save_license(redis, key, lic)
    redis.sadd("all_license_keys", key)

    return cors_response({
        "success": True,
        "key": key,
        "tier": tier,
        "tier_name": tier_info["name"],
        "expires_at": expires_at,
        "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S"),
        "max_machines": max_machines
    })


@app.route("/api/admin/keys", methods=["GET", "OPTIONS"])
def admin_list_keys():
    """List all license keys"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    redis = get_redis()
    all_keys = redis.smembers("all_license_keys")

    if not all_keys:
        return cors_response({"success": True, "keys": []})

    keys_data = []
    for key in all_keys:
        lic = get_license(redis, key)
        if not lic:
            continue

        tier = lic.get("tier", "basic")
        tier_info = TIERS.get(tier, TIERS["basic"])
        expires_at = lic.get("expires_at", 0)

        status = "active"
        if lic.get("revoked"):
            status = "revoked"
        elif time.time() > expires_at:
            status = "expired"

        keys_data.append({
            "key": key,
            "tier": tier,
            "tier_name": tier_info["name"],
            "status": status,
            "created_at": lic.get("created_at", 0),
            "created_at_human": datetime.fromtimestamp(lic.get("created_at", 0)).strftime("%Y-%m-%d %H:%M") if lic.get("created_at") else "N/A",
            "expires_at": expires_at,
            "expires_at_human": datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M") if expires_at else "N/A",
            "machines": lic.get("machines", []),
            "machine_count": len(lic.get("machines", [])),
            "max_machines": lic.get("max_machines_override") or tier_info["max_machines"],
            "last_validated": lic.get("last_validated"),
            "notes": lic.get("notes", "")
        })

    keys_data.sort(key=lambda x: x["created_at"], reverse=True)
    return cors_response({"success": True, "keys": keys_data})


@app.route("/api/admin/stats", methods=["GET", "OPTIONS"])
def admin_stats():
    """Dashboard statistics"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    redis = get_redis()
    all_keys = redis.smembers("all_license_keys")

    stats = {
        "total_keys": 0, "active": 0, "expired": 0, "revoked": 0,
        "trial": 0, "basic": 0, "pro": 0, "agency": 0,
        "total_machines": 0, "monthly_revenue": 0
    }

    if all_keys:
        stats["total_keys"] = len(all_keys)
        for key in all_keys:
            lic = get_license(redis, key)
            if not lic:
                continue
            tier = lic.get("tier", "basic")
            stats[tier] = stats.get(tier, 0) + 1
            stats["total_machines"] += len(lic.get("machines", []))

            if lic.get("revoked"):
                stats["revoked"] += 1
            elif time.time() > lic.get("expires_at", 0):
                stats["expired"] += 1
            else:
                stats["active"] += 1
                stats["monthly_revenue"] += TIERS.get(tier, {}).get("price", 0)

    return cors_response({"success": True, "stats": stats})


@app.route("/api/admin/revoke", methods=["POST", "OPTIONS"])
def admin_revoke():
    """Revoke a license key"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key:
        return cors_response({"success": False, "error": "Missing key"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Key not found"})

    lic["revoked"] = True
    lic["revoked_at"] = time.time()
    save_license(redis, key, lic)
    return cors_response({"success": True, "message": "License revoked"})


@app.route("/api/admin/extend", methods=["POST", "OPTIONS"])
def admin_extend():
    """Extend a license expiry"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    days = int(data.get("days", 30))
    if not key:
        return cors_response({"success": False, "error": "Missing key"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Key not found"})

    base_time = max(lic.get("expires_at", time.time()), time.time())
    new_expiry = base_time + (days * 86400)
    lic["expires_at"] = new_expiry
    lic["revoked"] = False
    save_license(redis, key, lic)

    return cors_response({
        "success": True,
        "message": f"License extended by {days} days",
        "new_expires_at": new_expiry,
        "new_expires_at_human": datetime.fromtimestamp(new_expiry).strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/admin/delete", methods=["POST", "OPTIONS"])
def admin_delete():
    """Permanently delete a license key"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key:
        return cors_response({"success": False, "error": "Missing key"}, 400)

    redis = get_redis()
    redis.delete(f"license:{key}")
    redis.srem("all_license_keys", key)
    return cors_response({"success": True, "message": "License deleted permanently"})


@app.route("/api/admin/deactivate", methods=["POST", "OPTIONS"])
def admin_deactivate_machine():
    """Remove a machine from a license"""
    if not verify_admin(request):
        return cors_response({"success": False, "error": "Unauthorized"}, 401)

    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()
    if not key or not hwid:
        return cors_response({"success": False, "error": "Missing key or hwid"}, 400)

    redis = get_redis()
    lic = get_license(redis, key)
    if not lic:
        return cors_response({"success": False, "error": "Key not found"})

    lic["machines"] = [m for m in lic.get("machines", []) if m["hwid"] != hwid]
    save_license(redis, key, lic)
    return cors_response({"success": True, "message": "Machine deactivated"})


@app.route("/api/health", methods=["GET", "OPTIONS"])
def health():
    return cors_response({"status": "ok", "service": "IG Tool License Server", "timestamp": time.time()})


@app.route("/", methods=["GET"])
def serve_dashboard():
    """Serve the admin dashboard HTML"""
    return send_from_directory(app.static_folder, 'index.html')
