"""Small reusable CustomTkinter building blocks shared by every tab."""

import customtkinter as ctk

from gui import theme


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.BG_CARD)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.BORDER)
        super().__init__(master, **kwargs)


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.ACCENT)
        kwargs.setdefault("hover_color", theme.ACCENT_HOVER)
        kwargs.setdefault("text_color", "#ffffff")
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 13, "bold"))
        super().__init__(master, **kwargs)


class SecondaryButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.BG_CARD_ALT)
        kwargs.setdefault("hover_color", theme.SIDEBAR_HOVER)
        kwargs.setdefault("text_color", theme.TEXT_PRIMARY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.BORDER)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        super().__init__(master, **kwargs)


class DangerButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.DANGER)
        kwargs.setdefault("hover_color", theme.DANGER_HOVER)
        kwargs.setdefault("text_color", "#ffffff")
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        super().__init__(master, **kwargs)


class StatusPill(ctk.CTkFrame):
    def __init__(self, master, text="", color=theme.TEXT_MUTED, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.dot = ctk.CTkLabel(self, text="●", text_color=color, font=(theme.FONT_FAMILY, 10))
        self.dot.pack(side="left", padx=(0, 6))
        self.label = ctk.CTkLabel(self, text=text, text_color=theme.TEXT_SECONDARY, font=(theme.FONT_FAMILY, 11))
        self.label.pack(side="left")

    def set(self, text, color):
        self.dot.configure(text_color=color)
        self.label.configure(text=text)


class SimpleTable(ctk.CTkScrollableFrame):
    """A minimal scrollable grid table: header row + data rows.

    columns: list of (key, heading, weight) tuples.
    Call set_rows(rows, cell_builder) to (re)populate. cell_builder, if given,
    is called as cell_builder(row_index, col_index, key, row_dict) and may
    return a widget for that cell (e.g. a dropdown or button row); returning
    None falls back to a plain text label using row_dict[key].
    """

    def __init__(self, master, columns, **kwargs):
        kwargs.setdefault("fg_color", theme.BG_INPUT)
        kwargs.setdefault("corner_radius", 10)
        super().__init__(master, **kwargs)
        self.columns = columns
        for i, (_, _, weight) in enumerate(columns):
            self.grid_columnconfigure(i, weight=weight)
        self._header_widgets = []
        self._data_rows = []
        self._rendered_key = None
        self._build_header()

    @staticmethod
    def _rows_key(rows):
        """A hashable fingerprint of the rendered data. Cell widgets built by
        cell_builder are a pure function of (row_index, col_index, key, row),
        so identical rows always render identically — safe to skip the
        rebuild entirely when nothing changed."""
        try:
            key = tuple(tuple(sorted(row.items())) for row in rows)
            hash(key)  # force the check — building the tuple alone won't raise
        except TypeError:
            return None  # unhashable value in a row — always rebuild
        return key

    def _build_header(self):
        for i, (_, heading, _) in enumerate(self.columns):
            lbl = ctk.CTkLabel(
                self,
                text=heading,
                anchor="w",
                text_color=theme.TEXT_SECONDARY,
                font=(theme.FONT_FAMILY, 11, "bold"),
            )
            lbl.grid(row=0, column=i, sticky="ew", padx=8, pady=(6, 10))
            self._header_widgets.append(lbl)

    def clear_rows(self):
        for widgets in self._data_rows:
            for w in widgets:
                w.destroy()
        self._data_rows = []

    def set_rows(self, rows, cell_builder=None, empty_text="Nothing here yet."):
        key = self._rows_key(rows)
        if key is not None and key == self._rendered_key:
            return
        self._rendered_key = key
        self.clear_rows()
        for r, row in enumerate(rows, start=1):
            row_widgets = []
            for c, (key, _, _) in enumerate(self.columns):
                widget = cell_builder(r - 1, c, key, row) if cell_builder else None
                if widget is None:
                    value = row.get(key, "")
                    widget = ctk.CTkLabel(
                        self,
                        text=str(value if value is not None else ""),
                        anchor="w",
                        text_color=theme.TEXT_PRIMARY,
                        font=(theme.FONT_FAMILY, 12),
                    )
                widget.grid(row=r, column=c, sticky="ew", padx=8, pady=4)
                row_widgets.append(widget)
            self._data_rows.append(row_widgets)
        if not rows:
            empty = ctk.CTkLabel(
                self, text=empty_text, text_color=theme.TEXT_MUTED, font=(theme.FONT_FAMILY, 12)
            )
            empty.grid(row=1, column=0, columnspan=len(self.columns), sticky="w", padx=8, pady=14)
            self._data_rows.append([empty])
