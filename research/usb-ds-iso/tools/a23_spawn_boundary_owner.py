"""Isolated repair for retained child with an interrupted stream-list assignment."""
from a23_terminal_owner import SamplerOwner as PreviousOwner


class SamplerOwner(PreviousOwner):
    def _cleanup(self, checkpoint):
        slot = self._slot
        if slot.child is not None:
            # Discover only streams on the actual retained object, never from a journal.
            for name in ('stdin', 'stdout', 'stderr'):
                stream = getattr(slot.child, name, None)
                if stream is not None and all(stream is not old for old in slot.streams):
                    slot.streams.append(stream)
        return super()._cleanup(checkpoint)
