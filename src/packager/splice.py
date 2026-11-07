"""Apply bounded byte-splice compatibility recipes to extracted inputs."""
import base64
from .core import BuildError


def apply(source, operations):
    output = bytearray()
    for operation in operations:
        if 'copy' in operation:
            offset, count = operation['copy']
            if offset < 0 or count < 0 or offset + count > len(source):
                raise BuildError('Resource splice refers outside the source')
            output.extend(source[offset:offset + count])
        elif 'data' in operation:
            output.extend(base64.b64decode(operation['data'], validate=True))
        else:
            raise BuildError('Unknown resource splice operation')
    return bytes(output)
