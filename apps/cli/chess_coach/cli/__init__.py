"""CHESS COACH command-line entrypoint package.

Invoke with ``python -m chess_coach.cli`` or via the ``chess-coach`` console
script installed by pyproject.toml.

Phase-1: a tiny dispatcher that knows two commands:
  ``chess-coach gateway``   - run the FastAPI gateway (same as `python -m chess_coach.gateway`)
  ``chess-coach migrate``   - run pending SQL migrations and exit
"""
