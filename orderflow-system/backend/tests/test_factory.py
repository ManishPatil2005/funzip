import pytest

from ofx.providers.factory import load_env_file, parse_angel_tokens, provider_from_env


def test_default_is_synthetic():
    assert provider_from_env({}) is None and provider_from_env({"OFX_PROVIDER": "synthetic"}) is None


def test_delta_needs_no_credentials():
    assert "Delta" in type(provider_from_env({"OFX_PROVIDER": "delta"})).__name__


def test_angel_requires_tokens_and_credentials():
    with pytest.raises(ValueError, match="ANGEL_TOKENS"):
        provider_from_env({"OFX_PROVIDER": "angel"})
    with pytest.raises(Exception, match="missing environment variables"):
        provider_from_env({"OFX_PROVIDER": "angel", "ANGEL_TOKENS": "NSE:SBIN-EQ=NSE:3045"})
    ok = {"OFX_PROVIDER": "angel", "ANGEL_TOKENS": "NSE:SBIN-EQ=NSE:3045", "ANGEL_SMARTAPI_KEY": "k", "ANGEL_CLIENT_ID": "c", "ANGEL_PASSWORD": "p", "ANGEL_TOTP_SECRET": "JBSWY3DPEHPK3PXP"}
    p = provider_from_env(ok)
    assert "k" not in repr(p) and "JBSW" not in repr(p)  # repr never leaks


def test_bad_values_rejected():
    with pytest.raises(ValueError):
        provider_from_env({"OFX_PROVIDER": "nope"})
    with pytest.raises(ValueError):
        parse_angel_tokens("garbage")
    assert parse_angel_tokens("NSE:A=NSE:1, NSE:B=NSE:2") == {"NSE:A": ("NSE", "1"), "NSE:B": ("NSE", "2")}


def test_env_file_does_not_override_real_environment(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# c\nA=1\nB='2'\n")
    env = {"A": "keep"}
    load_env_file(f, env)
    assert env == {"A": "keep", "B": "2"}
