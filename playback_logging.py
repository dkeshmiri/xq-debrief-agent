"""Playback diagnostics never perform output I/O on the callback thread."""
import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Full, Queue


class NonblockingQueueHandler(QueueHandler):
    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except Full:
            # Diagnostics may be dropped under overload; playback must not wait.
            pass


logger = logging.getLogger('xq.playback')
logger.setLevel(logging.INFO)
logger.propagate = False
_queue = Queue(maxsize=1000)
logger.addHandler(NonblockingQueueHandler(_queue))
_output = logging.StreamHandler()
_output.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))
_listener = QueueListener(_queue, _output)
_listener.start()
