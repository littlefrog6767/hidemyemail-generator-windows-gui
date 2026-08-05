"""Scheduler tab: generate a larger batch of addresses over time, pausing
and automatically resuming when Apple rate-limits creation."""

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLineEdit, QProgressBar, QTextEdit, QVBoxLayout, QWidget,
)

from gui import backend
from gui.widgets import Card, DangerButton, PrimaryButton, SecondaryButton, make_label

APPLE_MAX_PER_WINDOW = 5  # Apple allows at most 5 Hide My Email creations per 30 min
DEFAULT_BATCH_SIZE = APPLE_MAX_PER_WINDOW
DEFAULT_BATCH_DELAY_MINUTES = 30
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 300


class SchedulerView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._running = False
        self._paused = False
        self._cancelled = False
        self._target = 0
        self._remaining = 0
        self._generated_total = 0
        self._backoff_seconds = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
        self._delay_minutes = DEFAULT_BATCH_DELAY_MINUTES
        self._waiting = False
        self._wait_deadline = 0.0
        self._wait_reason = ""
        self._wait_variant = "secondary"
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)

        layout.addWidget(make_label("Scheduler", variant="heading"))
        layout.addWidget(make_label(
            "Generate a larger batch over time. Pauses and resumes automatically "
            "when Apple rate-limits creation.",
            variant="secondary",
        ))

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        inner = QGridLayout()
        inner.setVerticalSpacing(6)
        inner.setColumnStretch(1, 1)
        inner.setColumnStretch(3, 1)
        card_layout.addLayout(inner)

        inner.addWidget(make_label("BATCH DETAILS", variant="section"), 0, 0, 1, 4)
        note = make_label(
            f"Apple allows at most {APPLE_MAX_PER_WINDOW} new addresses per 30 minutes, "
            "so batch size is capped accordingly. You control the delay between batches.",
            variant="muted",
        )
        note.setWordWrap(True)
        inner.addWidget(note, 1, 0, 1, 4)

        inner.addWidget(make_label("Label", variant="secondary"), 2, 0)
        self.label_entry = QLineEdit("scheduled")
        inner.addWidget(self.label_entry, 3, 0)

        inner.addWidget(make_label("Total quantity", variant="secondary"), 2, 1)
        self.target_entry = QLineEdit("25")
        inner.addWidget(self.target_entry, 3, 1)

        inner.addWidget(make_label(f"Batch size (max {APPLE_MAX_PER_WINDOW})", variant="secondary"), 2, 2)
        self.batch_entry = QLineEdit(str(DEFAULT_BATCH_SIZE))
        inner.addWidget(self.batch_entry, 3, 2)

        inner.addWidget(make_label("Delay between batches (min)", variant="secondary"), 2, 3)
        self.delay_entry = QLineEdit(str(DEFAULT_BATCH_DELAY_MINUTES))
        inner.addWidget(self.delay_entry, 3, 3)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        inner.addWidget(self.progress_bar, 4, 0, 1, 4)

        self.progress_label = make_label("Not started.", variant="secondary")
        inner.addWidget(self.progress_label, 5, 0, 1, 4)

        btn_row = QHBoxLayout()
        self.start_btn = PrimaryButton("Start")
        self.start_btn.clicked.connect(self._start)
        self.pause_btn = SecondaryButton("Pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setEnabled(False)
        self.cancel_btn = DangerButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.pause_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        inner.addLayout(btn_row, 6, 0, 1, 4)

        layout.addWidget(card)

        log_card = Card()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(18, 14, 18, 18)
        log_layout.addWidget(make_label("ACTIVITY LOG", variant="section"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(self.log_box)
        layout.addWidget(log_card, stretch=1)

    def _log(self, message):
        self.log_box.append(message)

    def _set_progress_text(self, text, variant):
        self.progress_label.setText(text)
        self.progress_label.setProperty("variant", variant)
        self.progress_label.style().unpolish(self.progress_label)
        self.progress_label.style().polish(self.progress_label)

    def _set_controls_running(self, running):
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.pause_btn.setText("Pause")
        self.cancel_btn.setEnabled(running)

    def _start(self):
        if not self.app.app_state.is_signed_in:
            self._set_progress_text("Sign in first.", "danger")
            return
        try:
            target = max(1, int(self.target_entry.text()))
        except ValueError:
            target = 1
        try:
            batch_size = max(1, min(APPLE_MAX_PER_WINDOW, int(self.batch_entry.text())))
        except ValueError:
            batch_size = DEFAULT_BATCH_SIZE
        try:
            delay_minutes = max(0, float(self.delay_entry.text()))
        except ValueError:
            delay_minutes = DEFAULT_BATCH_DELAY_MINUTES
        self.target_entry.setText(str(target))
        self.batch_entry.setText(str(batch_size))
        self.delay_entry.setText(str(delay_minutes))

        self._target = target
        self._delay_minutes = delay_minutes
        self._remaining = target
        self._generated_total = 0
        self._backoff_seconds = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
        self._running = True
        self._paused = False
        self._cancelled = False
        self._waiting = False

        self.progress_bar.setValue(0)
        self.log_box.clear()
        self._log(
            f"Starting: {target} email(s) in batches of {batch_size}, "
            f"{delay_minutes:g} min between batches."
        )
        self._set_controls_running(True)
        self._run_batch()

    def _toggle_pause(self):
        if not self._running:
            return
        self._paused = not self._paused
        self.pause_btn.setText("Resume" if self._paused else "Pause")
        if self._paused:
            self._log("Paused by user.")
            self._set_progress_text("Paused.", "warning")
        else:
            self._log("Resumed.")
            if self._waiting:
                self._tick_wait()
            else:
                self._run_batch()

    def _cancel(self):
        if not self._running:
            return
        self._cancelled = True
        self._log("Cancelling…")

    def _run_batch(self):
        if self._cancelled:
            self._finish(cancelled=True)
            return
        if self._paused:
            return
        if self._remaining <= 0:
            self._finish(cancelled=False)
            return

        try:
            batch_size = max(1, min(APPLE_MAX_PER_WINDOW, int(self.batch_entry.text())))
        except ValueError:
            batch_size = DEFAULT_BATCH_SIZE
        requested = min(batch_size, self._remaining)
        self._log(f"Generating batch of {requested}…")
        self._set_progress_text(f"Generating… ({self._generated_total}/{self._target})", "secondary")
        self.app.worker.run_coro(
            backend.generate_emails(
                self.app.app_state.cookie_file, self.app.app_state.region,
                self.label_entry.text().strip() or "scheduled", requested,
            ),
            on_done=lambda result, error: self._on_batch_done(result, error, requested),
        )

    def _on_batch_done(self, result, error, requested):
        if self._cancelled:
            self._finish(cancelled=True)
            return

        if error is not None:
            self._log(f"Error: {error}. Retrying in {self._backoff_seconds}s…")
            self._schedule_retry()
            return

        got = len(result["emails"])
        self._generated_total += got
        self._remaining -= got
        self.progress_bar.setValue(int(min(1.0, self._generated_total / self._target) * 1000) if self._target else 0)
        self.app.on_addresses_changed()

        if got >= requested and result["ok"]:
            self._backoff_seconds = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
            self._log(f"Batch done — {got} generated ({self._generated_total}/{self._target} total).")
            if self._remaining <= 0:
                self._finish(cancelled=False)
                return
            self._start_wait(self._delay_minutes * 60, "Waiting for next batch", "secondary")
        else:
            err = result.get("error") or {}
            msg = err.get("message", "rate-limited")
            self._log(
                f"Only {got}/{requested} generated ({msg}). Apple's limit was reached — "
                f"stopping instead of hammering it, restarting the {self._delay_minutes:g} min timer."
            )
            self._start_wait(self._delay_minutes * 60, "Apple's limit was reached", "warning")

    def _start_wait(self, delay_seconds, reason, variant):
        # Used both for the normal pause between successful batches and for
        # the rate-limit recovery pause — same mechanism, different message/
        # color. Restarts the full configured interval rather than a short
        # reactive backoff, with a live countdown instead of a static message.
        self._waiting = True
        self._wait_deadline = time.monotonic() + delay_seconds
        self._wait_reason = reason
        self._wait_variant = variant
        self._tick_wait()

    def _tick_wait(self):
        if self._cancelled:
            self._waiting = False
            self._finish(cancelled=True)
            return
        if self._paused:
            return
        remaining = self._wait_deadline - time.monotonic()
        if remaining <= 0:
            self._waiting = False
            self._log(f"{self._wait_reason} — timer done, trying again.")
            self._run_batch()
            return
        mins, secs = divmod(int(remaining), 60)
        self._set_progress_text(
            f"{self._wait_reason} — trying again in {mins:02d}:{secs:02d} "
            f"({self._generated_total}/{self._target})",
            self._wait_variant,
        )
        QTimer.singleShot(1000, self._tick_wait)

    def _schedule_retry(self):
        delay = self._backoff_seconds
        self._backoff_seconds = min(MAX_BACKOFF_SECONDS, self._backoff_seconds * 1.5)
        self._set_progress_text(f"Retrying in {int(delay)}s…", "warning")
        QTimer.singleShot(int(delay * 1000), self._run_batch)

    def _finish(self, cancelled):
        self._running = False
        self._waiting = False
        self._set_controls_running(False)
        if cancelled:
            self._log(f"Cancelled. Generated {self._generated_total}/{self._target} total.")
            self._set_progress_text(
                f"Cancelled — {self._generated_total}/{self._target} generated.", "warning"
            )
        else:
            self._log(f"Done. Generated {self._generated_total}/{self._target} total.")
            self._set_progress_text(
                f"Done — {self._generated_total}/{self._target} generated.", "success"
            )
