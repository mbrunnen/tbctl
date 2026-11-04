from tbctl import state


def test_round_trip_per_key():
    state.save("a@https://a", {"auth": "jwt", "refresh_expires": 5})
    state.save("b@https://b", {"auth": "api-key"})
    assert state.load("a@https://a") == {"auth": "jwt", "refresh_expires": 5}
    assert state.load("missing") == {}


def test_empty_data_removes_the_key():
    state.save("a@https://a", {"auth": "jwt"})
    state.save("a@https://a", {})
    assert "a@https" not in (state.STATE_DIR / "state.toml").read_text()


def test_file_is_private():
    state.save("a@https://a", {"auth": "jwt"})
    assert (state.STATE_DIR / "state.toml").stat().st_mode & 0o777 == 0o600
    assert state.STATE_DIR.stat().st_mode & 0o777 == 0o700


def test_lock_path_lives_in_the_state_dir():
    path = state.lock_path("a%40https")
    assert path == state.STATE_DIR / "a%40https.lock"
    assert state.STATE_DIR.is_dir()


def test_save_keeps_a_concurrent_write_of_another_key(monkeypatch):
    """A save must not revert another context's table written in between."""
    import threading

    state.save("a@https://a", {"auth": "jwt"})
    real_all = state._all
    entered = threading.Event()
    release = threading.Event()

    def slow_all():
        data = real_all()
        if threading.current_thread().name == "slow":
            entered.set()
            release.wait(2)
        return data

    monkeypatch.setattr(state, "_all", slow_all)
    slow = threading.Thread(
        target=state.save, args=("a@https://a", {"auth": "api-key"}), name="slow"
    )
    slow.start()
    entered.wait(2)
    other = threading.Thread(target=state.save, args=("b@https://b", {"auth": "jwt"}))
    other.start()
    other.join(0.3)
    release.set()
    slow.join(2)
    other.join(2)
    assert state.load("b@https://b") == {"auth": "jwt"}
    assert state.load("a@https://a") == {"auth": "api-key"}
