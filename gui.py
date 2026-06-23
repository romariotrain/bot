"""
GUI-редактор правил на Tkinter (Фаза 4).

Визуальный аналог MFC-табов follow.exe: список правил, добавление правила
с выбором типа триггера, Start/Stop, живой стейт и лог ввода.
Tkinter входит в стандартный Python, на macOS работает из коробки.

Запуск:  python3 gui.py [profiles/demo.json]
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from backends import CallbackBackend, InputAction
from engine import Engine, EventTrigger, Rule, StateTrigger, TimedTrigger
from profiles import _OPS, build_rule, load_profile
from state import StateProvider


class BotGUI:
    def __init__(self, root: tk.Tk, profile_path: str | None = None) -> None:
        self.root = root
        root.title("rule-engine — учебный аналог follow.exe")
        root.geometry("760x560")

        self.provider = StateProvider()
        self.rules: list[Rule] = []
        self.engine: Engine | None = None
        self._inq: queue.Queue[InputAction] = queue.Queue()

        self._build_widgets()
        if profile_path:
            self._load(profile_path)
        self._poll_inputs()
        self._poll_state()

    # ----------------------------------------------------------- layout
    def _build_widgets(self) -> None:
        # верхняя панель кнопок
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        ttk.Button(top, text="Load…", command=self._on_load).pack(side="left")
        ttk.Button(top, text="Save…", command=self._on_save).pack(side="left", padx=4)
        self.btn_start = ttk.Button(top, text="▶ Start", command=self._on_start)
        self.btn_start.pack(side="left", padx=12)
        self.btn_stop = ttk.Button(top, text="■ Stop", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left")
        self.lbl_state = ttk.Label(top, text="state: —", font=("Menlo", 11))
        self.lbl_state.pack(side="right")

        # таблица правил (= табы оригинала, но в одном списке)
        mid = ttk.Frame(self.root, padding=6)
        mid.pack(fill="both", expand=True)
        cols = ("name", "trigger", "actions", "cd")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (220, 200, 140, 80)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        # кнопки управления правилами
        rb = ttk.Frame(self.root, padding=(6, 0))
        rb.pack(fill="x")
        ttk.Button(rb, text="+ Add rule", command=self._on_add).pack(side="left")
        ttk.Button(rb, text="− Remove", command=self._on_remove).pack(side="left", padx=4)

        # лог ввода
        ttk.Label(self.root, text="Input log:", padding=(6, 4)).pack(anchor="w")
        self.log = tk.Text(self.root, height=10, font=("Menlo", 10), state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # ----------------------------------------------------------- helpers
    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rules):
            trig = type(r.trigger).__name__.replace("Trigger", "")
            acts = "+".join(a.key for a in r.actions)
            self.tree.insert("", "end", iid=str(i),
                             values=(r.name, trig, acts, r.cooldown_ms))

    def _logline(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ----------------------------------------------------------- polling
    def _poll_inputs(self) -> None:
        import time
        while not self._inq.empty():
            a = self._inq.get_nowait()
            hold = f" (hold {a.hold_ms}ms)" if a.hold_ms else ""
            self._logline(f"[{time.strftime('%H:%M:%S')}] INPUT -> {a.key}{hold}")
        self.root.after(50, self._poll_inputs)

    def _poll_state(self) -> None:
        s = self.provider.read()
        self.lbl_state.configure(
            text=f"state: hp={s.hp:.2f} mana={s.mana:.2f} "
                 f"enemies={s.enemies_near} zone={s.zone}")
        self.root.after(200, self._poll_state)

    # ----------------------------------------------------------- actions
    def _on_load(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        try:
            self.rules, _ = load_profile(path)
            self._refresh_tree()
            self._logline(f"loaded profile: {path} ({len(self.rules)} rules)")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _on_save(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        import json
        # минимальная сериализация обратно в JSON
        out = {"tick_ms": 50, "rules": []}
        for r in self.rules:
            out["rules"].append(getattr(r, "_src", {"name": r.name,
                                "trigger": {"type": "timed", "min_ms": 1000, "max_ms": 1000},
                                "actions": [a.key for a in r.actions]}))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        self._logline(f"saved: {path}")

    def _on_add(self) -> None:
        AddRuleDialog(self.root, self._add_rule)

    def _add_rule(self, cfg: dict) -> None:
        rule = build_rule(cfg)
        rule._src = cfg  # запомним исходный JSON для сохранения
        self.rules.append(rule)
        self._refresh_tree()

    def _on_remove(self) -> None:
        sel = self.tree.selection()
        if sel:
            del self.rules[int(sel[0])]
            self._refresh_tree()

    def _on_start(self) -> None:
        if not self.rules:
            messagebox.showinfo("Нет правил", "Сначала загрузи или добавь правила.")
            return
        backend = CallbackBackend(self._inq.put)
        self.engine = Engine(backend, self.provider, self.rules, tick_ms=50)
        self.engine.start()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._logline("[engine] started")

    def _on_stop(self) -> None:
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._logline("[engine] stopped")


class AddRuleDialog(tk.Toplevel):
    """Мини-форма добавления правила: тип триггера + параметры + клавиши."""

    def __init__(self, parent, on_ok) -> None:
        super().__init__(parent)
        self.title("Add rule")
        self.on_ok = on_ok
        self.resizable(False, False)
        pad = {"padx": 6, "pady": 3}

        ttk.Label(self, text="Name").grid(row=0, column=0, sticky="w", **pad)
        self.name = ttk.Entry(self, width=28); self.name.grid(row=0, column=1, **pad)
        self.name.insert(0, "my-rule")

        ttk.Label(self, text="Trigger").grid(row=1, column=0, sticky="w", **pad)
        self.ttype = ttk.Combobox(self, values=["timed", "state", "event"],
                                  state="readonly", width=25)
        self.ttype.grid(row=1, column=1, **pad); self.ttype.current(0)
        self.ttype.bind("<<ComboboxSelected>>", lambda e: self._render_params())

        self.params = ttk.Frame(self); self.params.grid(row=2, column=0, columnspan=2, **pad)
        self._pw: dict[str, tk.Widget] = {}

        ttk.Label(self, text="Keys (comma)").grid(row=3, column=0, sticky="w", **pad)
        self.keys = ttk.Entry(self, width=28); self.keys.grid(row=3, column=1, **pad)
        self.keys.insert(0, "X")

        ttk.Label(self, text="Cooldown ms").grid(row=4, column=0, sticky="w", **pad)
        self.cd = ttk.Entry(self, width=28); self.cd.grid(row=4, column=1, **pad)
        self.cd.insert(0, "0")

        ttk.Button(self, text="Add", command=self._submit).grid(
            row=5, column=0, columnspan=2, pady=8)
        self._render_params()

    def _render_params(self) -> None:
        for w in self.params.winfo_children():
            w.destroy()
        self._pw.clear()
        t = self.ttype.get()
        if t == "timed":
            self._field("min_ms", "4000"); self._field("max_ms", "4300")
        elif t == "state":
            self._field("field", "hp"); self._combo("op", list(_OPS)); self._field("value", "0.35")
        elif t == "event":
            self._field("field", "zone")

    def _field(self, name, default) -> None:
        row = len(self._pw)
        ttk.Label(self.params, text=name).grid(row=row, column=0, sticky="w")
        e = ttk.Entry(self.params, width=18); e.grid(row=row, column=1)
        e.insert(0, default); self._pw[name] = e

    def _combo(self, name, values) -> None:
        row = len(self._pw)
        ttk.Label(self.params, text=name).grid(row=row, column=0, sticky="w")
        c = ttk.Combobox(self.params, values=values, state="readonly", width=15)
        c.grid(row=row, column=1); c.current(0); self._pw[name] = c

    def _submit(self) -> None:
        t = self.ttype.get()
        trig: dict = {"type": t}
        try:
            if t == "timed":
                trig |= {"min_ms": int(self._pw["min_ms"].get()),
                         "max_ms": int(self._pw["max_ms"].get())}
            elif t == "state":
                trig |= {"field": self._pw["field"].get(),
                         "op": self._pw["op"].get(),
                         "value": float(self._pw["value"].get()), "edge": True}
            elif t == "event":
                trig |= {"field": self._pw["field"].get()}
            cfg = {
                "name": self.name.get(),
                "trigger": trig,
                "actions": [k.strip() for k in self.keys.get().split(",") if k.strip()],
                "cooldown_ms": int(self.cd.get() or 0),
            }
            self.on_ok(cfg)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Bad input", str(e))


def main() -> None:
    profile = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    BotGUI(root, profile)
    root.mainloop()


if __name__ == "__main__":
    main()
