# src/cache/rest_cache.py
# REST position scripts loaded at startup by motion_io (like fingerspelling cache)

REST_LEFT = {
    "token": "REST_LEFT",
    "type": "STATIC",
    "duration": 0.5,
    "keyframes": [{
        "time": 0.0,
        "L": [90, 90, 90, 90, 90],
        "LW": [90, 90],
        "LE": [90],
        "LS": [90, 90]
    }]
}

REST_RIGHT = {
    "token": "REST_RIGHT",
    "type": "STATIC",
    "duration": 0.5,
    "keyframes": [{
        "time": 0.0,
        "R": [90, 90, 90, 90, 90],
        "RW": [90, 90],
        "RE": [90],
        "RS": [90, 90]
    }]
}
