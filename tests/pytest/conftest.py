import os
import subprocess
import pytest


def pytest_addoption(parser):
    """Add CLI options to inject API key and base URL into the test session.

    Usage examples:
      poetry run pytest -qs tests/pytest --api-key <KEY>
      poetry run pytest -qs tests/pytest --api-key <KEY> --api-base-url https://lespass.tibillet.localhost
    """
    parser.addoption(
        "--api-key",
        action="store",
        default=None,
        help="API key to use for Authorization header (sets env var API_KEY)",
    )
    parser.addoption(
        "--api-base-url",
        action="store",
        default=None,
        help="Override base URL for API tests (sets env var API_BASE_URL)",
    )


@pytest.fixture(autouse=True, scope="session")
def _inject_cli_env(request):
    """Autouse session fixture to export CLI options into environment vars.

    Tests already read API_KEY and API_BASE_URL from the environment, so
    this allows passing them via pytest CLI flags without editing tests.
    """

    api_key = request.config.getoption("--api-key") or os.getenv("API_KEY")

    if not api_key:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "lespass_django",
                "poetry",
                "run",
                "python",
                "manage.py",
                "test_api_key",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(
                "Unable to fetch API key from docker. "
                "Command failed: docker exec lespass_django poetry run python manage.py test_api_key\n"
                f"stderr: {result.stderr.strip()}"
            )
        api_key = result.stdout.strip()

    if not api_key:
        pytest.fail(
            "API key is empty. Provide --api-key/ API_KEY env or ensure docker "
            "returns a key via manage.py test_api_key."
        )

    os.environ["API_KEY"] = api_key

    base = request.config.getoption("--api-base-url")
    if base:
        os.environ["API_BASE_URL"] = base.rstrip("/")


def pytest_collection_modifyitems(config, items):
    """
    Reorder tests to ensure the following sequence for API v2 Event flow:
    1) create
    2) list
    3) retrieve
    4) link (address linking)
    5) delete
    Other tests keep their relative order.
    """

    def sort_key(item):
        name = item.name.lower()
        path = str(item.fspath)
        # Priority by function/test name
        if "create" in name:
            return (0, path)
        if "list" in name:
            return (1, path)
        if "retrieve" in name:
            return (2, path)
        # ensure link-address tests run before delete cleanup
        if "link" in name:
            return (3, path)
        if "delete" in name:
            return (4, path)
        # Everything else afterwards
        return (10, path)

    items.sort(key=sort_key)
