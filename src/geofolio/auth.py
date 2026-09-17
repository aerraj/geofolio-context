"""Small-team shared-role access keys and expiring, signed HttpOnly sessions."""

import hashlib
import hmac
import secrets
import time


class Access:
    def __init__(self, admin, viewer=None):
        self.admin, self.viewer = admin, viewer
        self.signing_key = secrets.token_bytes(32)

    def key_role(self, key):
        if not key:
            return None
        if self.admin and secrets.compare_digest(key, self.admin):
            return "admin"
        if self.viewer and secrets.compare_digest(key, self.viewer):
            return "viewer"
        return None

    def session(self, role):
        payload = f"{role}:{int(time.time()) + 28800}:{secrets.token_hex(16)}"
        return payload + ":" + hmac.new(self.signing_key, payload.encode(), hashlib.sha256).hexdigest()

    def role(self, headers, cookies):
        bearer = headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            return self.key_role(bearer[7:])
        cookie = cookies.get("geofolio_session", "")
        try:
            role, expiry, nonce, signature = cookie.split(":")
            payload = f"{role}:{expiry}:{nonce}"
            expected = hmac.new(self.signing_key, payload.encode(), hashlib.sha256).hexdigest()
            if (
                role in {"admin", "viewer"}
                and int(expiry) > time.time()
                and hmac.compare_digest(signature, expected)
            ):
                return role
        except (ValueError, TypeError):
            pass
        return None
