"""Transaction boundaries shared by capability execution and event projection."""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def isolated_savepoint(env):
    """Isolate one attempt without flushing caller state before a rollback boundary.

    Odoo's default ``cr.savepoint()`` flushes *before* issuing ``SAVEPOINT``.  A failed
    pre-flush can therefore poison the transaction outside the intended boundary.  The
    outer non-flushing savepoint below guards that baseline flush; the inner savepoint owns
    only the isolated attempt.  On attempt rollback, clearing the ORM cache is safe because
    all earlier dirty state was flushed between the two savepoints and remains present in
    the transaction.

    Transport-only contexts without an Odoo cursor retain the same no-op behavior.
    """

    cursor = getattr(env, "cr", None)
    savepoint = getattr(cursor, "savepoint", None)
    flush = getattr(cursor, "flush", None)
    clear = getattr(cursor, "clear", None)
    if not callable(savepoint) or not callable(flush) or not callable(clear):
        yield
        return

    attempt_error = None
    try:
        with savepoint(flush=False):
            flush()
            try:
                with savepoint(flush=False):
                    yield
                    flush()
            except BaseException as error:  # noqa: BLE001 - rollback must cover cancellation
                attempt_error = (error, error.__traceback__)
                clear()
    except BaseException:
        clear()
        raise
    if attempt_error is not None:
        error, traceback = attempt_error
        raise error.with_traceback(traceback)
