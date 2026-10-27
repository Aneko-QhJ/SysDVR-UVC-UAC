"""Offline main-thread SIGINT deferral around the pinned pre-retained constructor."""
import signal
import threading

from a23_preretained_owner import SamplerOwner as PreviousOwner
import a23_terminal_deadline as prior


class SamplerOwner(PreviousOwner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._saved_mask = None
        self._mask_thread = None
        self._slot.state.update(sigint_guard_entered=False, original_sigint_blocked=None,
            mask_install_attempted=False, mask_installed=False, mask_restore_verified=False,
            mask_restore_exceptions=[])

    def _restore_mask(self):
        if self._saved_mask is None:
            return None
        prior.require(threading.get_ident() == self._mask_thread, 'mask_thread_mismatch')
        first = None
        try:
            signal.pthread_sigmask(signal.SIG_SETMASK, self._saved_mask)
        except BaseException as exc:
            first = exc
            self._slot.state['mask_restore_exceptions'].append(type(exc).__name__)
        try:
            current = signal.pthread_sigmask(signal.SIG_BLOCK, set())
            verified = current == self._saved_mask
            self._slot.state['mask_restore_verified'] = verified
            if verified:
                self._saved_mask = None
        except BaseException as exc:
            self._slot.state['mask_restore_verified'] = False
            self._slot.state['mask_restore_exceptions'].append(type(exc).__name__)
            if first is None:
                first = exc
        if self._saved_mask is not None and first is None:
            first = prior.Rejected('mask_restore_unverified')
        return first

    def _create(self, *args, **kwargs):
        prior.require(threading.current_thread() is threading.main_thread() and threading.active_count() == 1,
                      'sigint_guard_requires_single_python_main_thread')
        prior.require(signal.getsignal(signal.SIGINT) is signal.default_int_handler,
                      'sigint_guard_requires_default_handler')
        # Save before changing the mask. A failure cannot erase the original mask value.
        self._saved_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        self._mask_thread = threading.get_ident()
        state = self._slot.state
        state.update(sigint_guard_entered=True, original_sigint_blocked=signal.SIGINT in self._saved_mask,
                     mask_install_attempted=True)
        primary = None
        child = None
        try:
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
            state['mask_installed'] = True
            child = super()._create(*args, **kwargs)
        except BaseException as exc:
            primary = exc
        restore_error = self._restore_mask()
        if primary is not None:
            raise primary
        if restore_error is not None:
            raise restore_error
        return child

    def finish(self, **kwargs):
        if self._saved_mask is not None:
            prior.require(threading.get_ident() == self._mask_thread, 'mask_thread_mismatch')
        primary = self._restore_mask()
        try:
            result = super().finish(**kwargs)
        except BaseException as exc:
            if primary is None:
                primary = exc
        if primary is not None:
            raise primary
        return result
