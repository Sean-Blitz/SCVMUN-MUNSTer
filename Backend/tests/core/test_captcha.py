"""Unit tests for ``core.captcha.verify``.

This is the one function in the backend that decides whether a human check passed, and it has
three jobs that are easy to conflate:

* **is the check configured?** no secret means "disabled, everyone passes" (development);
  a secret with no hostname allow-list means "reject everything" (fail closed, by design);
* **is the token plausible?** missing or over-long tokens are refused *before* a network call,
  so a hostile client cannot make the server post megabytes;
* **what did Cloudflare say?** only ``success: true``, for an allow-listed hostname, for the
  expected action, counts as passed. A network failure is **not** the same as a failed check:
  it raises ``CaptchaUnavailable`` so the route can answer 503 rather than blaming the visitor.

No test here touches the network: ``core.captcha.urlopen`` is replaced by a fake that records
the request and replays a canned body, which also lets the outgoing form be asserted.
"""

import json
from urllib.error import URLError
from urllib.parse import parse_qs

import pytest

import core.captcha as captcha


class _FakeResponse:
    """The little bit of the ``urlopen`` context manager that ``verify`` uses."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class FakeSiteverify:
    """Stands in for ``urlopen``: records every call and replays one canned answer."""

    def __init__(self):
        self.calls: list[tuple[object, float]] = []
        self.body = b"{}"
        self.error: Exception | None = None

    def answer(self, *, success: bool = True, hostname: str = "localhost", action: str = "auth"):
        self.body = json.dumps(
            {"success": success, "hostname": hostname, "action": action}
        ).encode("utf-8")

    def raw(self, body: bytes):
        self.body = body

    def raises(self, error: Exception):
        self.error = error

    def __call__(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.body)


@pytest.fixture()
def configured(monkeypatch):
    """A deployment with a secret and a hostname allow-list."""
    monkeypatch.setenv("TURNSTILE_SECRET", "test-secret")
    monkeypatch.setenv("TURNSTILE_HOSTNAMES", "localhost,scvmun.esuhsd.org")


@pytest.fixture()
def siteverify(monkeypatch):
    fake = FakeSiteverify()
    monkeypatch.setattr(captcha, "urlopen", fake)
    return fake


# ---------------------------------------------------------------------------
# Is the check configured?
# ---------------------------------------------------------------------------


def test_without_a_secret_every_token_passes(monkeypatch, siteverify):
    """Development and the test suite run this way: the gate is off, not failed."""
    monkeypatch.setenv("TURNSTILE_SECRET", "")

    assert captcha.enabled() is False
    assert captcha.verify(None) is True
    assert siteverify.calls == []


def test_a_secret_without_hostnames_rejects_everything(configured, monkeypatch, siteverify):
    """Fail closed on a half-done deployment.

    With nothing to compare against, accepting any hostname Cloudflare reports would make the
    check theatre - so every token is refused, and nothing is sent to Cloudflare either.
    """
    monkeypatch.setenv("TURNSTILE_HOSTNAMES", "")

    assert captcha.verify("a-token") is False
    assert siteverify.calls == []


def test_the_secret_is_read_at_call_time(monkeypatch):
    """A module-level constant used to read an empty environment at import and silently
    disable the check, so this reads the variable every call."""
    monkeypatch.setenv("TURNSTILE_SECRET", "")
    assert captcha.enabled() is False

    monkeypatch.setenv("TURNSTILE_SECRET", "rotated-secret")
    assert captcha.enabled() is True


def test_hostnames_are_split_and_stripped(monkeypatch):
    monkeypatch.setenv("TURNSTILE_HOSTNAMES", " A.example ,, B.example ,")

    assert captcha.allowed_hostnames() == ("a.example", "b.example")


# ---------------------------------------------------------------------------
# The token is plausible?
# ---------------------------------------------------------------------------


def test_a_missing_token_is_rejected(configured, siteverify):
    assert captcha.verify(None) is False
    assert siteverify.calls == []


def test_an_over_long_token_is_rejected_before_any_request(configured, siteverify):
    """The documented maximum is enforced locally, so a hostile client cannot make us post
    megabytes to Cloudflare."""
    assert captcha.verify("x" * (captcha.MAX_TOKEN_LENGTH + 1)) is False
    assert siteverify.calls == []


def test_a_token_at_the_limit_is_sent(configured, siteverify):
    """The boundary is "longer than", not "as long as"."""
    siteverify.answer()

    assert captcha.verify("x" * captcha.MAX_TOKEN_LENGTH) is True
    assert len(siteverify.calls) == 1


# ---------------------------------------------------------------------------
# What Cloudflare said
# ---------------------------------------------------------------------------


def test_a_genuine_token_passes(configured, siteverify):
    siteverify.answer()

    assert captcha.verify("the-token") is True


def test_an_unsuccessful_verification_is_rejected(configured, siteverify):
    siteverify.answer(success=False)

    assert captcha.verify("the-token") is False


def test_a_hostname_outside_the_allow_list_is_rejected(configured, siteverify):
    """The token may be genuine - it was just minted somewhere we do not serve from."""
    siteverify.answer(hostname="attacker.example")

    assert captcha.verify("the-token") is False


def test_hostname_matching_ignores_case(configured, monkeypatch, siteverify):
    monkeypatch.setenv("TURNSTILE_HOSTNAMES", "SCVMUN.ESUHSD.ORG")
    siteverify.answer(hostname="scvmun.esuhsd.org")

    assert captcha.verify("the-token") is True


def test_a_token_minted_for_another_action_is_rejected(configured, siteverify):
    """One widget serves both auth buttons, and Siteverify echoes the action back."""
    siteverify.answer(action="login")

    assert captcha.verify("the-token") is False


def test_a_custom_expected_action_is_honoured(configured, siteverify):
    siteverify.answer(action="login")

    assert captcha.verify("the-token", expected_action="login") is True


def test_an_empty_expected_action_skips_the_action_check(configured, siteverify):
    """Passing "" is how a caller says "any action will do"."""
    siteverify.answer(action="something-else")

    assert captcha.verify("the-token", expected_action="") is True


def test_a_payload_that_is_not_an_object_is_rejected(configured, siteverify):
    """A JSON array parses fine but has no ``success`` key; it must not raise."""
    siteverify.raw(b"[]")

    assert captcha.verify("the-token") is False


# ---------------------------------------------------------------------------
# Failures are not the same as a failed check
# ---------------------------------------------------------------------------


def test_a_body_that_is_not_json_raises_unavailable(configured, siteverify):
    """A garbled reply is our problem, not the visitor's - hence 503, not 400."""
    siteverify.raw(b"<html>not json</html>")

    with pytest.raises(captcha.CaptchaUnavailable):
        captcha.verify("the-token")


def test_a_network_failure_raises_unavailable(configured, siteverify):
    """URLError is an OSError, which is what the module catches."""
    siteverify.raises(URLError("connection timed out"))

    with pytest.raises(captcha.CaptchaUnavailable):
        captcha.verify("the-token")


# ---------------------------------------------------------------------------
# What is sent to Cloudflare
# ---------------------------------------------------------------------------


def test_the_request_is_a_form_post_carrying_the_secret_and_token(configured, siteverify):
    siteverify.answer()

    captcha.verify("the-token")

    (request, timeout) = siteverify.calls[0]
    assert request.full_url == captcha.SITEVERIFY_URL
    assert request.get_method() == "POST"
    assert timeout == captcha.TIMEOUT_SECONDS

    fields = parse_qs(request.data.decode("utf-8"))
    assert fields["secret"] == ["test-secret"]
    assert fields["response"] == ["the-token"]
    assert "remoteip" not in fields


def test_the_client_ip_is_forwarded_when_known(configured, siteverify):
    """Siteverify can weigh the request's origin; the route passes `request.client.host`."""
    siteverify.answer()

    captcha.verify("the-token", "203.0.113.5")

    (request, _timeout) = siteverify.calls[0]
    fields = parse_qs(request.data.decode("utf-8"))
    assert fields["remoteip"] == ["203.0.113.5"]
