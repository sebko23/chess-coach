"""Polyglot opening-book IO for the chess-coach gateway.

This package houses the read/write primitives for Polyglot ``.bin``
opening books, plus (in subsequent BBFs) the higher-level abstractions
that the gateway routes use to surface books to callers.

The current contents are the WRITE side (see
:mod:`chess_coach.repertoire.polyglot_writer`). The READ side is
the python-chess library's ``chess.polyglot.open_reader`` and
``chess.polyglot.zobrist_hash``, which are already used by the α
route (``repertoire_recommendations.py``). A future BBF (FU-11
α-ext+ path) may add a ``BookIndex`` abstraction here that wraps
the read path with a cache layer; that's not in scope for FU-7
α or for the BBF-FU-11b initial implementation.

BBF-FU-11b (Tier 2 of FU-11, per the BBF-FU-11 decision brief
in ``docs/16_audit/``): the gateway routes
``/v1/repertoire/{player}/book`` import
:func:`chess_coach.repertoire.polyglot_writer.write_polyglot_book`
and :class:`chess_coach.repertoire.polyglot_writer.BookEntry` to
write a per-player book file at ``data_dir/books/<player>.bin``.
"""
