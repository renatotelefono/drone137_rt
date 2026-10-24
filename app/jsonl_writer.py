"""Bounded diagnostic recording without file I/O on a control event loop."""
import json
from pathlib import Path
import queue
import threading


class JsonlWriter:
    """Enqueue immutable records; close waits for ordered, complete persistence.

    Overflow and writer failure are explicit. Records are never silently dropped.
    Call close outside a time-critical event loop (for example via to_thread).
    """
    def __init__(self,path,max_pending=128,opener=open):
        self.path=Path(path);self.queue=queue.Queue(maxsize=max_pending)
        self.opener=opener;self.error=None;self.closed=False
        self.thread=threading.Thread(target=self._run,daemon=True,name='drone137-recorder')
        self.thread.start()

    def _check(self):
        if self.error is not None:raise RuntimeError('Diagnostic recording failed: '+str(self.error))

    def write(self,record):
        self._check()
        if self.closed:raise RuntimeError('Diagnostic recording is closed')
        try:self.queue.put_nowait(record)
        except queue.Full as exc:raise RuntimeError('Diagnostic recording queue is full') from exc

    def _run(self):
        try:
            with self.opener(self.path,'w') as stream:
                while True:
                    record=self.queue.get()
                    if record is None:break
                    stream.write(json.dumps(record,allow_nan=False)+'\n')
                    stream.flush()
        except Exception as exc:self.error=exc

    def close(self,timeout=20):
        self._check()
        if not self.closed:
            self.closed=True
            try:self.queue.put(None,timeout=timeout)
            except queue.Full as exc:raise RuntimeError('Diagnostic recording could not drain') from exc
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():raise RuntimeError('Diagnostic recording did not finish')
        self._check()
