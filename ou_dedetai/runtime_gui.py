"""Tk runtime picker. Filesystem and version work stays off the Tk thread."""
from functools import partial
from pathlib import Path
from queue import Empty, Queue
import threading
from typing import Callable, cast
from tkinter import StringVar, Toplevel, filedialog, font, messagebox, ttk

from ou_dedetai import runtime
from ou_dedetai.app import App, UserExitedFromAsk


class RuntimePicker:
    def __init__(self, app):
        self.app = app
        self.lock = runtime.selection_lock(app)
        if not self.lock.acquire(blocking=False):
            app.status('Finish the current installation or runtime selection first.')
            return
        self.window = Toplevel(app.root)
        self.window.title('Select Wine runtime')
        self.window.configure(background=ttk.Style(self.window).lookup('TFrame', 'background'))
        self.window.geometry('1000x430')
        self.window.minsize(600, 300)
        self.window.transient(app.root)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        self.events: Queue[Callable[[], None]] = Queue()
        self.options = []
        self.recommended = None
        self.recommendation = None
        self.releases: list[runtime.AppImageRelease] = []
        self.busy = True
        self.closed = False
        self.status = StringVar(value='Finding installed runtimes…')
        self.instruction_font = font.nametofont('TkDefaultFont', root=self.window).copy()
        self.instruction_font.configure(weight='bold')
        ttk.Label(self.window, textvariable=self.status, font=self.instruction_font).grid(
            row=0, column=0, sticky='w', padx=10, pady=8)
        frame = ttk.Frame(self.window)
        frame.grid(row=1, column=0, sticky='nsew', padx=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.list = ttk.Treeview(frame, show='tree', selectmode='browse')
        self.list.tag_configure('current', font=self.instruction_font)
        self.list.tag_configure('missing', foreground='gray')
        self.list.column('#0', stretch=False)
        self.list.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(frame, orient='vertical', command=self.list.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.list.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.list.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.list.bind('<<TreeviewSelect>>', self.highlight)
        self.path = StringVar()
        ttk.Entry(self.window, textvariable=self.path, state='readonly').grid(
            row=2, column=0, sticky='ew', padx=10, pady=8)
        buttons = ttk.Frame(self.window)
        buttons.grid(row=3, column=0, sticky='e', padx=10, pady=10)
        self.select_button = ttk.Button(buttons, text='Select', command=self.select, state='disabled')
        self.select_button.pack(side='left', padx=5)
        self.add_button = ttk.Button(buttons, text='Add new…', command=self.add, state='disabled')
        self.add_button.pack(side='left', padx=5)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda event: self.close())
        self.window.bind('<Return>', lambda event: self.select())
        self.window.after(50, self.poll)
        self.work(lambda: runtime.runtime_options(app), self.loaded)
        self.work(lambda: runtime.recommended_appimage(app), self.set_recommended)
        self.work(lambda: runtime.available_appimages(app), self.set_releases)

    def work(self, operation, complete):
        def run():
            try:
                result = operation()
            except Exception as error:
                self.events.put(partial(self.failed, error))
            else:
                self.events.put(lambda: complete(result))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            while not self.closed:
                self.events.get_nowait()()
        except Empty:
            pass
        if not self.closed:
            self.window.after(50, self.poll)

    def loaded(self, options):
        self.options = options
        runtime.include_releases(self.app, self.options, self.releases)
        runtime.include_recommended(self.app, self.options, self.recommendation)
        self.set_busy(False)
        self.redraw(next((i for i, item in enumerate(options) if item.current), None))
        for option in options:
            self.probe(option)

    def probe(self, option):
        if option.path and option.path.suffix.lower() != '.appimage':
            self.work(lambda: runtime.runtime_version(option.path),
                      lambda version: self.version_ready(option, version))

    def version_ready(self, option, version):
        option.version = version
        self.redraw()

    def set_recommended(self, release):
        self.recommendation = release
        self.recommended = release[0] if release else None
        runtime.include_recommended(self.app, self.options, release)
        self.redraw()

    def set_releases(self, releases):
        self.releases = releases
        runtime.include_releases(self.app, self.options, releases)
        self.redraw()

    def redraw(self, index=None):
        if index is None:
            selected = self.list.selection()
            index = int(selected[0]) if selected else None
        x = self.list.xview()[0]
        y = self.list.yview()[0]
        self.list.delete(*self.list.get_children())
        width = 0
        for row, option in enumerate(self.options):
            option.recommended = option.path is not None and option.path.name == self.recommended
            tags = ('current',) if option.current else (('missing',) if option.path is None else ())
            self.list.insert('', 'end', iid=str(row), text=option.label, tags=tags)
            width = max(width, self.instruction_font.measure(option.label) + 24)
        self.list.column('#0', width=width)
        if index is not None:
            self.list.selection_set(str(index))
        self.list.xview_moveto(x)
        self.list.yview_moveto(y)
        self.highlight()

    def highlight(self, event=None):
        selected = self.list.selection()
        option = self.options[int(selected[0])] if selected else None
        if option is not None and option.path is None:
            self.list.selection_remove(*selected)
            option = None
        self.path.set(str(option.path) if option else '')
        self.select_button.configure(state='normal' if option and not self.busy else 'disabled')

    def set_busy(self, busy):
        self.busy = busy
        self.add_button.configure(state='disabled' if busy else 'normal')
        self.status.set('Downloading or validating runtime…' if busy else 'Choose a runtime, then press Select.')
        self.highlight()

    def add(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self.window, title='Choose an AppImage or Wine executable',
            initialdir=runtime.downloads_directory(),
            filetypes=[('AppImages', ('*.AppImage', '*.appimage')), ('All files', '*')])
        if not path:
            return
        self.set_busy(True)
        self.work(lambda: runtime.added_runtime(Path(path)), self.added)

    def added(self, option):
        self.set_busy(False)
        if option.path.suffix.lower() != '.appimage' and option.server is None:
            server = self.choose_server()
            if server is None:
                return
            option.server = server
        # A file choice follows through immediately, without another Select step.
        self.activate(option)

    def choose_server(self):
        value = filedialog.askopenfilename(
            parent=self.window, title='Choose the matching wineserver executable',
            initialdir=runtime.downloads_directory(), filetypes=[('All files', '*')])
        return Path(value) if value else None

    def select(self):
        selected = self.list.selection()
        if self.busy or not selected:
            return
        option = self.options[int(selected[0])]
        if option.path is None:
            return
        if option.current:
            self.close()
            return
        self.activate(option)

    def activate(self, option):
        if option.path.suffix.lower() != '.appimage' and option.server is None:
            option.server = runtime._server_for(option.path) or self.choose_server()
            if option.server is None:
                return
        self.set_busy(True)
        # Activation can ask for approval. Marshal that prompt and status updates
        # through the queue, so the worker never calls Tk.
        self.work(lambda: runtime.activate_option(cast(App, _PickerApp(self)), option), self.activated)

    def activated(self, result):
        self.busy = False
        self.close()

    def failed(self, error):
        self.set_busy(False)
        if not isinstance(error, UserExitedFromAsk):
            messagebox.showerror('Wine selection failed', str(error), parent=self.window)

    def close(self):
        if self.busy:
            return
        self.closed = True
        self.window.destroy()
        self.lock.release()


class _PickerApp:
    def __init__(self, picker):
        self.picker = picker

    def __getattr__(self, name):
        return getattr(self.picker.app, name)

    def approve(self, question, context=None):
        answer: Queue[bool] = Queue()
        self.picker.events.put(lambda: answer.put(messagebox.askyesno(
            'Confirm Wine runtime', question + ('\n' + context if context else ''), parent=self.picker.window)))
        return answer.get()

    def status(self, message, percent=None):
        def update():
            self.picker.status.set(message)
            self.picker.app.status(message, percent)
        self.picker.events.put(update)
