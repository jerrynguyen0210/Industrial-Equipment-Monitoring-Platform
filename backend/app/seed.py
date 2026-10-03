"""Compatibility CLI for python -m app.seed; implementation lives in app.db.seed."""

from app.db.seed import main

if __name__ == "__main__":
    main()
