"""Test package shim for source package imports.

Pytest can put ``tests/`` ahead of the repo root for modules under this
directory, which makes ``import hermes_cli`` resolve here instead of the source
package.  Keep the package path pointed at the real implementation so tests
that import ``cli`` or ``hermes_cli.main`` exercise production code.
"""

from pathlib import Path

_SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "hermes_cli"
if str(_SOURCE_PACKAGE) not in __path__:
    __path__.insert(0, str(_SOURCE_PACKAGE))

__version__ = "0.10.0"
__release_date__ = "2026.4.16"
