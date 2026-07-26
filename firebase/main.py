"""Firebase Functions (Python) — Supervisorly subject-map endpoint.

Deploy:
  1. In your Firebase project: `firebase init functions` and choose **Python**.
  2. Replace the generated `functions/main.py` and `functions/requirements.txt`
     with these two files (or copy this folder's contents there).
  3. `firebase deploy --only functions`

The endpoint:
  GET  /subject_map?field=NLP&email=you@example.com
  POST /subject_map   {"field": "NLP", "email": "you@example.com"}

`email` may be omitted if SUPERVISORLY_CONTACT_EMAIL is set as a function env var:
  firebase functions:secrets:set SUPERVISORLY_CONTACT_EMAIL
(or set it in the Firebase console). It is used only for the OpenAlex polite
pool — see docs/DECISIONS.md D-019.
"""

import json

from firebase_functions import https_fn
from supervisorly.webapi import CORS_HEADERS, handle_subject_map


@https_fn.on_request()
def subject_map(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":                              # CORS preflight
        return https_fn.Response("", status=204, headers=CORS_HEADERS)
    if req.method == "GET":
        params = dict(req.args)
    else:
        params = req.get_json(silent=True) or {}
    status, body = handle_subject_map(params)
    return https_fn.Response(
        json.dumps(body, ensure_ascii=False),
        status=status,
        headers={**CORS_HEADERS, "Content-Type": "application/json; charset=utf-8"},
    )
