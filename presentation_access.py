"""Operator PIN gate for the prepared presentation page and its API."""
import hmac
import os
import secrets
from threading import Lock
from time import monotonic

from flask import jsonify, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE = 'xq_presentation_operator'
ACCESS_SECONDS = 8 * 60 * 60


def protect_presentation(blueprint):
    # Restarting the app invalidates prior grants. No PIN goes into the cookie.
    signer = URLSafeTimedSerializer(secrets.token_bytes(32), salt='presentation-operator')
    failures = {}
    lock = Lock()

    def authorized():
        token = request.cookies.get(COOKIE)
        if not token:
            return False
        try:
            return signer.loads(token, max_age=ACCESS_SECONDS) == 'operator'
        except (BadSignature, SignatureExpired):
            return False

    @blueprint.get('/api/presentation/access')
    def operator_access():
        return jsonify(unlocked=authorized())

    @blueprint.post('/api/presentation/unlock')
    def operator_unlock():
        if not request.is_json:
            return jsonify(error='Enter your operator PIN.'), 415
        payload = request.get_json(silent=True)
        pin = payload.get('pin') if isinstance(payload, dict) else None
        expected = os.getenv('XQ_PRESENTATION_PIN', '2020')
        now = monotonic()
        address = request.remote_addr or 'local'
        with lock:
            for key in list(failures):
                if now - failures[key][1] >= 60:
                    del failures[key]
            count, since = failures.get(address, (0, now))
            if count >= 5:
                return jsonify(error='Too many attempts. Wait a minute and try again.'), 429
            if not isinstance(pin, str) or len(pin) > 64 or not hmac.compare_digest(pin.encode(), expected.encode()):
                failures[address] = (count + 1, since)
                return jsonify(error='Incorrect operator PIN.'), 403
            failures.pop(address, None)
        response = jsonify(unlocked=True)
        response.set_cookie(COOKIE, signer.dumps('operator'), httponly=True,
                            secure=request.is_secure, samesite='Strict', path='/')
        return response

    @blueprint.before_request
    def require_operator():
        if request.endpoint in ('presentation.operator_access', 'presentation.operator_unlock'):
            return None
        if not authorized():
            if request.path == '/presentation':
                return redirect('/#presentation-access')
            return jsonify(error='Enter your operator PIN to access Presentation Mode.'), 403

    @blueprint.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        return response
