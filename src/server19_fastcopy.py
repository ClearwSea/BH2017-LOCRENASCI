"""Copy internal JSON graphs in C / 用C实现复制内部JSON对象。

Temporary marshal bytes never leave memory. Explicit memo and non-JSON
objects retain copy.deepcopy semantics, including custom copy hooks.
"""
from copy import deepcopy as _original
import marshal


def deepcopy(value, memo=None):
    if memo is not None:
        return _original(value, memo)
    # Only internal verified JSON trees use this helper. Unsupported objects
    # fall back rather than entering a persisted or external marshal format.
    try:
        return marshal.loads(marshal.dumps(value, 4))
    except (TypeError, ValueError):
        return _original(value)
