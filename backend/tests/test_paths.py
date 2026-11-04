import sqlite3

from src import paths


def test_data_dir_override_and_legacy_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLICAT_DATA_DIR", str(tmp_path / "data"))
    assert paths.data_dir() == tmp_path / "data"
    target = paths.database_path()
    assert target == tmp_path / "data" / "publicat.db"

    legacy = tmp_path / "legacy.db"
    con = sqlite3.connect(legacy)
    con.execute("create table t (x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()

    assert paths.migrate_legacy_database(target, legacy) is True
    assert legacy.exists(), "legacy file must be left in place"
    assert sqlite3.connect(target).execute("select x from t").fetchone() == (42,)
    # second start: nothing to do, existing target untouched
    assert paths.migrate_legacy_database(target, legacy) is False


def test_no_legacy_means_fresh_database_url(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLICAT_DATA_DIR", str(tmp_path / "fresh"))
    assert paths.migrate_legacy_database(paths.database_path(), tmp_path / "missing.db") is False
    url = paths.default_database_url()
    assert url.endswith("/fresh/publicat.db") and (tmp_path / "fresh").is_dir()
