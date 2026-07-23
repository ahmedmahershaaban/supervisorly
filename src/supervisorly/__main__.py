"""Enable ``python -m supervisorly`` — a console-script-free entry point.

Useful on machines where pip can't write the ``supervisorly`` executable into a
global Scripts directory, and inside CI / the clean-room verification.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
