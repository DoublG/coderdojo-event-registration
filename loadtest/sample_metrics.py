"""Samples the site's /metrics/ every 2 seconds during a load test (loadtest/run.sh):
MySQL's open connections, the memory (PSS) of the web and Celery processes
and Redis's memory, one JSON line per sample. A sample the site refused (a
503 from the concurrency cap) is recorded as `refused`.

    METRICS_TOKEN=... python3 sample_metrics.py https://<site>/metrics/ out.jsonl
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

URL, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ["METRICS_TOKEN"]
LINE = re.compile(r"^(\w+)(?:\{([^}]*)\})? (\S+)$")


def read():
    request = urllib.request.Request(URL, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        text = response.read().decode()
    sample = {"db_connections": None, "pss_mb": {}, "redis_mb": None}
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        name, labels, value = match.groups()
        if name == "coderdojo_mysql_threads_connected":
            sample["db_connections"] = int(float(value))
        elif name == "coderdojo_redis_used_memory_bytes":
            sample["redis_mb"] = round(float(value) / 2**20, 1)
        elif name == "coderdojo_process_pss_bytes":
            role = re.search(r'role="([^"]+)"', labels).group(1)
            group = "web" if role == "web" else "celery"
            sample["pss_mb"][group] = round(sample["pss_mb"].get(group, 0) + float(value) / 2**20)
    return sample


with open(OUT, "a") as out:
    while True:
        started = time.time()
        try:
            sample = read()
        except urllib.error.HTTPError as error:
            sample = {"refused": error.code}
        except Exception as error:  # the site is struggling: that's a data point too
            sample = {"error": type(error).__name__}
        out.write(json.dumps({"t": round(started, 2), **sample}) + "\n")
        out.flush()
        time.sleep(max(0, 2 - (time.time() - started)))
