import pytest


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
