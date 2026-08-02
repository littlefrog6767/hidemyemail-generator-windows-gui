"""Scheduler tab: generate a larger batch of addresses over time, pausing
and automatically resuming when Apple rate-limits creation."""

import customtkinter as ctk

from gui import backend, theme
from gui.widgets import Card, PrimaryButton, SecondaryButton, DangerButton

APPLE_MAX_PER_WINDOW = 5  # Apple allows at most 5 Hide My Email creations per 30 min
DEFAULT_BATCH_SIZE = APPLE_MAX_PER_WINDOW
DEFAULT_BATCH_DELAY_MINUTES = 30
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 300


class SchedulerView(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._running = False
        self._paused = False
        self._cancelled = False
        self._target = 0
        self._remaining = 0
        self._generated_total = 0
        self._backoff_seconds = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
        self._delay_minutes = DEFAULT_BATCH_DELAY_MINUTES
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 10))
        ctk.CTkLabel(
            header, text="Scheduler", font=(theme.FONT_FAMILY, 22, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Generate a larger batch over time. Pauses and resumes automatically when Apple rate-limits creation.",
            text_color=theme.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        card = Card(self)
        card.pack(fill="x", padx=28, pady=10)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=22, pady=20)
        inner.grid_columnconfigure(1, weight=1)
        inner.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            inner, text="BATCH DETAILS", text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            inner,
            text=f"Apple allows at most {APPLE_MAX_PER_WINDOW} new addresses per 30 minutes, "
                 "so batch size is capped accordingly. You control the delay between batches.",
            text_color=theme.TEXT_MUTED, font=(theme.FONT_FAMILY, 11), wraplength=560, justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ctk.CTkLabel(inner, text="Label", text_color=theme.TEXT_SECONDARY).grid(
            row=2, column=0, sticky="w", pady=6
        )
        self.label_var = ctk.StringVar(value="scheduled")
        ctk.CTkEntry(
            inner, textvariable=self.label_var, fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 6))

        ctk.CTkLabel(inner, text="Total quantity", text_color=theme.TEXT_SECONDARY).grid(
            row=2, column=1, sticky="w", pady=6, padx=(18, 0)
        )
        self.target_var = ctk.StringVar(value="25")
        ctk.CTkEntry(
            inner, textvariable=self.target_var, fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        ).grid(row=3, column=1, sticky="ew", pady=(0, 6), padx=(18, 0))

        ctk.CTkLabel(
            inner, text=f"Batch size (max {APPLE_MAX_PER_WINDOW})", text_color=theme.TEXT_SECONDARY,
        ).grid(row=2, column=2, sticky="w", pady=6, padx=(18, 0))
        self.batch_var = ctk.StringVar(value=str(DEFAULT_BATCH_SIZE))
        ctk.CTkEntry(
            inner, textvariable=self.batch_var, fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        ).grid(row=3, column=2, sticky="ew", pady=(0, 6), padx=(18, 0))

        ctk.CTkLabel(inner, text="Delay between batches (min)", text_color=theme.TEXT_SECONDARY).grid(
            row=2, column=3, sticky="w", pady=6, padx=(18, 0)
        )
        self.delay_var = ctk.StringVar(value=str(DEFAULT_BATCH_DELAY_MINUTES))
        ctk.CTkEntry(
            inner, textvariable=self.delay_var, fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        ).grid(row=3, column=3, sticky="ew", pady=(0, 6), padx=(18, 0))

        self.progress_bar = ctk.CTkProgressBar(inner, fg_color=theme.BG_INPUT, progress_color=theme.ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(14, 6))

        self.progress_label = ctk.CTkLabel(inner, text="Not started.", text_color=theme.TEXT_SECONDARY)
        self.progress_label.grid(row=5, column=0, columnspan=4, sticky="w")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.grid(row=6, column=0, columnspan=4, sticky="w", pady=(14, 0))
        self.start_btn = PrimaryButton(btn_row, text="Start", command=self._start)
        self.start_btn.pack(side="left")
        self.pause_btn = SecondaryButton(btn_row, text="Pause", command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=(10, 0))
        self.cancel_btn = DangerButton(btn_row, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(10, 0))

        log_card = Card(self)
        log_card.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        ctk.CTkLabel(
            log_card, text="ACTIVITY LOG", text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).pack(anchor="w", padx=18, pady=(14, 4))
        self.log_box = ctk.CTkTextbox(
            log_card, fg_color=theme.BG_INPUT, border_width=1, border_color=theme.BORDER,
            corner_radius=8,
        )
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.log_box.configure(state="disabled")

    def _log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_controls_running(self, running):
        self.start_btn.configure(state="disabled" if running else "normal")
        self.pause_btn.configure(state="normal" if running else "disabled", text="Pause")
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _start(self):
        if not self.app.app_state.is_signed_in:
            self.progress_label.configure(text="Sign in first.", text_color=theme.DANGER)
            return
        try:
            target = max(1, int(self.target_var.get()))
        except ValueError:
            target = 1
        try:
            batch_size = max(1, min(APPLE_MAX_PER_WINDOW, int(self.batch_var.get())))
        except ValueError:
            batch_size = DEFAULT_BATCH_SIZE
        try:
            delay_minutes = max(0, float(self.delay_var.get()))
        except ValueError:
            delay_minutes = DEFAULT_BATCH_DELAY_MINUTES
        self.target_var.set(str(target))
        self.batch_var.set(str(batch_size))
        self.delay_var.set(str(delay_minutes))

        self._target = target
        self._delay_minutes = delay_minutes
        self._remaining = target
        self._generated_total = 0
        self._backoff_seconds = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
        self._running = True
        self._paused = False
        self._cancelled = False

        self.progress_bar.set(0)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
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
        self.pause_btn.configure(text="Resume" if self._paused else "Pause")
        if self._paused:
            self._log("Paused by user.")
            self.progress_label.configure(text="Paused.", text_color=theme.WARNING)
        else:
            self._log("Resumed.")
            self._run_batch()

    def _get_delay_ms(self):
        return max(0, int(self._delay_minutes * 60 * 1000))

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
            batch_size = max(1, min(APPLE_MAX_PER_WINDOW, int(self.batch_var.get())))
        except ValueError:
            batch_size = DEFAULT_BATCH_SIZE
        requested = min(batch_size, self._remaining)
        self._log(f"Generating batch of {requested}…")
        self.progress_label.configure(
            text=f"Generating… ({self._generated_total}/{self._target})", text_color=theme.TEXT_SECONDARY
        )
        self.app.worker.run_coro(
            backend.generate_emails(
                self.app.app_state.cookie_file, self.app.app_state.region, self.label_var.get().strip() or "scheduled",
                requested,
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
        self.progress_bar.set(min(1.0, self._generated_total / self._target) if self._target else 0)
        self.app.on_addresses_changed()

        if got >= requested and result["ok"]:
            self._backoff_seconds = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
            self._log(f"Batch done — {got} generated ({self._generated_total}/{self._target} total).")
            if self._remaining <= 0:
                self._finish(cancelled=False)
                return
            delay_ms = self._get_delay_ms()
            self._log(f"Waiting {self._delay_minutes:g} min before next batch…")
            self.progress_label.configure(
                text=f"Waiting {self._delay_minutes:g} min… ({self._generated_total}/{self._target})",
                text_color=theme.TEXT_SECONDARY,
            )
            self.after(delay_ms, self._run_batch)
        else:
            err = result.get("error") or {}
            retry_after = err.get("retry_after") or self._backoff_seconds
            self._backoff_seconds = min(MAX_BACKOFF_SECONDS, max(retry_after, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS) * 1.5)
            msg = err.get("message", "rate-limited")
            self._log(
                f"Only {got}/{requested} generated ({msg}). Pausing {int(retry_after)}s before resuming…"
            )
            self.progress_label.configure(
                text=f"Rate-limited — resuming in {int(retry_after)}s ({self._generated_total}/{self._target})",
                text_color=theme.WARNING,
            )
            self.after(int(retry_after * 1000), self._run_batch)

    def _schedule_retry(self):
        delay = self._backoff_seconds
        self._backoff_seconds = min(MAX_BACKOFF_SECONDS, self._backoff_seconds * 1.5)
        self.progress_label.configure(text=f"Retrying in {int(delay)}s…", text_color=theme.WARNING)
        self.after(int(delay * 1000), self._run_batch)

    def _finish(self, cancelled):
        self._running = False
        self._set_controls_running(False)
        if cancelled:
            self._log(f"Cancelled. Generated {self._generated_total}/{self._target} total.")
            self.progress_label.configure(
                text=f"Cancelled — {self._generated_total}/{self._target} generated.", text_color=theme.WARNING
            )
        else:
            self._log(f"Done. Generated {self._generated_total}/{self._target} total.")
            self.progress_label.configure(
                text=f"Done — {self._generated_total}/{self._target} generated.", text_color=theme.SUCCESS
            )
