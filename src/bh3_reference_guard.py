"""Reference recipes are retained for porting to the standalone builder."""
import os
def require_reference_mode(module):
    if os.environ.get('BH3_ENABLE_REFERENCE_RECIPES') != '1':
        raise RuntimeError('Reference recipe requires explicit input/path migration: '+module+'. See docs/build.md.')
