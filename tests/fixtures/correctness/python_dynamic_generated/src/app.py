from importlib import import_module


def load_runtime():
    return import_module("runtime_pkg")
