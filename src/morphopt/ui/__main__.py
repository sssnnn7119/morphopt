"""Allow ``python -m morphopt.ui`` to launch the definition workbench."""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
