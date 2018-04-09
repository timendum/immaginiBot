"""Utils class and costants"""
import re
import signal

from praw.models.util import BoundedSet # pylint: disable=W0611

STATIC_EXT = ['jpeg', 'jpg', 'png']
ANIM_EXT = ['gif', 'avi', 'gifv']
ALL_EXT = STATIC_EXT + ANIM_EXT

ANIM_RE = re.compile(r'\.(%s)$' % ('|'.join(ANIM_EXT)), re.IGNORECASE)
STATIC_RE = re.compile(r'\.(%s)$' % ('|'.join(STATIC_EXT)), re.IGNORECASE)

MAYBE_IMAGE = re.compile(r'(?:^|\s|\^)(\w+)\.(%s)\b' % ('|'.join(ALL_EXT)), re.IGNORECASE)

class GracefulDeath:  # pylint: disable=R0903
    """Catch signals to allow graceful shutdown."""

    def __init__(self):
        self.last_signal = self.received_kill = None
        catch_signals = [signal.SIGINT, signal.SIGTERM]
        for signum in catch_signals:
            try:
                signal.signal(signum, self.handler)
            except ValueError:
                pass

    def handler(self, signum, frame):
        """Riceve signals"""
        _ = frame
        self.last_signal = signum
        self.received_kill = True
