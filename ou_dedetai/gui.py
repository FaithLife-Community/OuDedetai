from tkinter import Toplevel
from tkinter import BooleanVar
from tkinter import font
from tkinter import IntVar
from tkinter import messagebox
from tkinter import simpledialog
from tkinter import StringVar
from tkinter import Text
from tkinter.ttk import Button
from tkinter.ttk import Checkbutton
from tkinter.ttk import Combobox
from tkinter.ttk import Frame
from tkinter.ttk import Label
from tkinter.ttk import Progressbar
from tkinter.ttk import Radiobutton
from tkinter.ttk import Separator

from ou_dedetai.app import App

from . import constants


class ChoiceGui(Frame):
    _default_prompt: str = "Choose…"

    def __init__(self, root, question: str, options: list[str], **kwargs):
        super(ChoiceGui, self).__init__(root, **kwargs)
        self.italic = font.Font(slant='italic')
        self.config(padding=5)
        self.grid(row=0, column=0, sticky='nwes')

        # Label Row
        self.question_label = Label(self, text=question)
        # drop-down menu
        self.answer_var = StringVar(value=self._default_prompt)
        self.answer_dropdown = Combobox(self, textvariable=self.answer_var)
        self.answer_dropdown['values'] = options
        if len(options) > 0:
            self.answer_dropdown.set(options[0])

        # Cancel/Okay buttons row.
        self.cancel_button = Button(self, text="Cancel")
        self.okay_button = Button(self, text="Confirm")

        # Place widgets.
        row = 0
        self.question_label.grid(column=0, row=row, sticky='nws', pady=2, padx=8)
        self.answer_dropdown.grid(column=1, row=row, sticky='w', pady=2, columnspan=2)
        row += 1
        self.cancel_button.grid(column=1, row=row, sticky='e', pady=2)
        self.okay_button.grid(column=2, row=row, sticky='e', pady=2)


class InfoGui(Frame):
    _default_prompt: str = "Info"

    def __init__(self, root, message: str, **kwargs):
        super(InfoGui, self).__init__(root, **kwargs)
        self.italic = font.Font(slant='italic')
        self.config(padding=5)
        self.grid(row=0, column=0, sticky='nwes')

        # Label Row
        h = len(message.split('\n')) - 1
        self.info_text = Text(self, height=h)
        self.info_text.insert(1.0, message)
        self.info_text.config(state='disabled')

        # Cancel/Okay buttons row.
        self.okay_button = Button(self, text="Okay")

        # Place widgets.
        row = 0
        self.info_text.grid(column=0, row=row, sticky='nws', pady=2, padx=8)
        row += 1
        self.okay_button.grid(column=2, row=row, sticky='e', pady=2)


class InstallerGui(Frame):
    def __init__(self, root, app: App, **kwargs):
        super(InstallerGui, self).__init__(root, **kwargs)

        self.italic = font.Font(slant='italic')
        self.config(padding=5)
        self.grid(row=0, column=0, sticky='nwes')

        self.app = app

        # Product/Version row.
        self.product_label = Label(self, text="Product & Version: ")
        # product drop-down menu
        self.productvar = StringVar(value='Choose product…')
        self.product_dropdown = Combobox(self, textvariable=self.productvar)
        self.product_dropdown.state(['readonly'])
        self.product_dropdown['values'] = ('Logos', 'Verbum')
        if app.conf._raw.faithlife_product in self.product_dropdown['values']:
            self.product_dropdown.set(app.conf._raw.faithlife_product)
        # version drop-down menu
        self.versionvar = StringVar()
        self.version_dropdown = Combobox(
            self,
            width=5,
            textvariable=self.versionvar
        )
        self.version_dropdown.state(['readonly'])
        #TODO: Remove this dropdown
        self.version_dropdown['values'] = ('10')
        self.versionvar.set(self.version_dropdown['values'][0])
        if app.conf._raw.faithlife_product_version in self.version_dropdown['values']:
            self.version_dropdown.set(app.conf._raw.faithlife_product_version)

        # Release row.
        self.release_label = Label(self, text="Release: ")
        # release drop-down menu
        self.releasevar = StringVar(value='Choose release…')
        self.release_dropdown = Combobox(self, textvariable=self.releasevar)
        self.release_dropdown.state(['readonly'])
        self.release_dropdown['values'] = []
        if app.conf._raw.faithlife_product_release:
            self.release_dropdown['values'] = [app.conf._raw.faithlife_product_release]
            self.releasevar.set(app.conf._raw.faithlife_product_release)

        # Wine row.
        self.wine_label = Label(self, text="Wine exe: ")
        self.winevar = StringVar()
        self.wine_dropdown = Combobox(self, textvariable=self.winevar)
        self.wine_dropdown.state(['readonly'])
        self.wine_dropdown['values'] = []
        # Conditional only if wine_binary is actually set, don't prompt if it's not
        if self.app.conf._raw.wine_binary:
            self.wine_dropdown['values'] = [self.app.conf.wine_binary]
            self.winevar.set(self.app.conf.wine_binary)

        # Skip Dependencies row.
        self.skipdeps_label = Label(self, text="Install Dependencies: ")
        self.skipdepsvar = BooleanVar(value=not self.app.conf.skip_install_system_dependencies) #noqa: E501
        self.skipdeps_checkbox = Checkbutton(self, variable=self.skipdepsvar)

        # Cancel/Okay buttons row.
        self.cancel_button = Button(self, text="Cancel")
        self.okay_button = Button(self, text="Install")
        self.okay_button.state(['disabled'])

        # Place widgets.
        row = 0
        self.product_label.grid(column=0, row=row, sticky='nws', pady=2)
        self.product_dropdown.grid(column=1, row=row, sticky='w', pady=2)
        self.version_dropdown.grid(column=2, row=row, sticky='w', pady=2)
        row += 1
        self.release_label.grid(column=0, row=row, sticky='w', pady=2)
        self.release_dropdown.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.wine_label.grid(column=0, row=row, sticky='w', pady=2)
        self.wine_dropdown.grid(column=1, row=row, columnspan=3, sticky='we', pady=2)  # noqa: E501
        row += 1
        self.skipdeps_label.grid(column=0, row=row, sticky='nws', pady=2)
        self.skipdeps_checkbox.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.cancel_button.grid(column=3, row=row, sticky='e', pady=2)
        self.okay_button.grid(column=4, row=row, sticky='e', pady=2)
        row += 1

class StatusGui(Frame):
    def __init__(self, root, *args, **kwargs):
        super(StatusGui, self).__init__(root, **kwargs)
        self.config(padding=5)
        self.grid(row=0, column=0, sticky='nwes')

        self.statusvar = StringVar()
        self.message_label = Label(self, textvariable=self.statusvar, wraplength=350, justify="left") #noqa: E501
        # Progress bar
        self.progressvar = IntVar(value=0)
        self.progress = Progressbar(
            self,
            mode='indeterminate',
            orient='horizontal',
            variable=self.progressvar,
            # This length sets the minimum length of the progress bar
            length=350
        )
        self.progress.state(['disabled'])


class StatusWithLabelGui(StatusGui):
    def __init__(self, root, label: str, *args, **kwargs):
        super(StatusWithLabelGui, self).__init__(root, **kwargs)

        self.app_label = Label(self, text=label, font=('TkDefaultFont', 16))
        self.app_label.grid(column=0, row=0, sticky='we', pady=2)
        Separator(self, orient='horizontal').grid(column=0, row=1, sticky='ew')
        self.message_label.grid(column=0, row=2, sticky='we', pady=2)
        self.progress.grid(column=0, row=3, sticky='we', pady=2)


class ControlGui(StatusGui):
    def __init__(self, root, *args, **kwargs):
        super(ControlGui, self).__init__(root, **kwargs)

        # Run/install app button
        self.app_buttonvar = StringVar()
        self.app_buttonvar.set("Install")
        self.app_label = Label(self, text="FaithLife app")
        self.app_button = Button(self, textvariable=self.app_buttonvar)

        self.app_install_advancedvar = StringVar()
        self.app_install_advancedvar.set("Advanced Install")
        self.app_install_advanced = Button(self, textvariable=self.app_install_advancedvar) #noqa: E501

        # Installed app actions
        # -> Run indexing, Remove library catalog, Remove all index files
        s1 = Separator(self, orient='horizontal')
        self.actionsvar = StringVar()
        self.actions_label = Label(self, text="App actions: ")
        self.run_indexing_radio = Radiobutton(
            self,
            text="Run indexing",
            variable=self.actionsvar,
            value='run-indexing',
        )
        self.remove_library_catalog_radio = Radiobutton(
            self,
            text="Remove library catalog",
            variable=self.actionsvar,
            value='remove-library-catalog',
        )
        self.remove_index_files_radio = Radiobutton(
            self,
            text="Remove all index files",
            variable=self.actionsvar,
            value='remove-index-files',
        )
        self.install_icu_radio = Radiobutton(
            self,
            text="Install/Update ICU files",
            variable=self.actionsvar,
            value='install-icu',
        )
        self.actions_button = Button(self, text="Run action")
        self.actions_button.state(['disabled'])
        s2 = Separator(self, orient='horizontal')

        # Edit config button
        self.config_label = Label(self, text="Edit config file")
        self.config_button = Button(self, text="Edit …")
        # Install deps button
        self.deps_label = Label(self, text="Install dependencies")
        self.deps_button = Button(self, text="Install")
        # Backup/restore data buttons
        self.backups_label = Label(self, text="Backup/restore data")
        self.backup_button = Button(self, text="Backup")
        self.restore_button = Button(self, text="Restore")
        # The normal text has three lines. Make this the same 
        # in order for tkinker to know how large to draw it
        self.update_lli_label = Label(self, text=f"Update {constants.APP_NAME}\n\n")  # noqa: E501
        self.update_lli_button = Button(self, text="Update")
        # AppImage buttons
        self.latest_appimage_label = Label(
            self,
            text="Update to Latest AppImage"
        )
        self.latest_appimage_button = Button(self, text="Run")
        self.set_appimage_label = Label(self, text="Set AppImage")
        self.set_appimage_button = Button(self, text="Run")
        # App logging toggle
        self.loggingstatevar = StringVar(value='Enable')
        self.logging_label = Label(self, text="Toggle app logging")
        self.logging_button = Button(self, textvariable=self.loggingstatevar)
        # Support options
        self.support_state_var = StringVar(value='Get Support')
        self.support_label = Label(self, text="Troubleshooting")
        self.support_button = Button(self, textvariable=self.support_state_var)
        # Separator
        s3 = Separator(self, orient='horizontal')

        # Place widgets.
        row = 0
        self.app_label.grid(column=0, row=row, sticky='w', pady=2)
        self.app_button.grid(column=1, row=row, sticky='w', pady=2)
        self.show_advanced_install_button()
        row += 1
        s1.grid(column=0, row=1, columnspan=3, sticky='we', pady=2)
        row += 1
        self.actions_label.grid(column=0, row=row, sticky='e', padx=20, pady=2)
        self.run_indexing_radio.grid(column=1, row=row, sticky='w', pady=2, columnspan=2)  # noqa: E501
        row += 1
        self.remove_library_catalog_radio.grid(column=1, row=row, sticky='w', pady=2, columnspan=2)  # noqa: E501
        row += 1
        self.actions_button.grid(column=0, row=row, sticky='e', padx=20, pady=2)  # noqa: E501
        self.remove_index_files_radio.grid(column=1, row=row, sticky='w', pady=2, columnspan=2)  # noqa: E501
        row += 1
        self.install_icu_radio.grid(column=1, row=row, sticky='w', pady=2, columnspan=2)  # noqa: E501
        row += 1
        s2.grid(column=0, row=row, columnspan=3, sticky='we', pady=2)
        row += 1
        self.config_label.grid(column=0, row=row, sticky='w', pady=2)
        self.config_button.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.deps_label.grid(column=0, row=row, sticky='w', pady=2)
        self.deps_button.grid(column=1, row=row, sticky='w', pady=2)
        # row += 1
        # self.backups_label.grid(column=0, row=row, sticky='w', pady=2)
        # self.backup_button.grid(column=1, row=row, sticky='w', pady=2)
        # self.restore_button.grid(column=2, row=row, sticky='w', pady=2)
        row += 1
        self.update_lli_label.grid(column=0, row=row, sticky='w', pady=2)
        self.update_lli_button.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.latest_appimage_label.grid(column=0, row=row, sticky='w', pady=2)
        self.latest_appimage_button.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.set_appimage_label.grid(column=0, row=row, sticky='w', pady=2)
        self.set_appimage_button.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.logging_label.grid(column=0, row=row, sticky='w', pady=2)
        self.logging_button.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        self.support_label.grid(column=0, row=row, sticky='w', pady=2)
        self.support_button.grid(column=1, row=row, sticky='w', pady=2)
        row += 1
        s3.grid(column=0, row=row, columnspan=3, sticky='we', pady=2)
        row += 1
        self.message_label.grid(column=0, row=row, columnspan=3, sticky='we', pady=2)  # noqa: E501
        row += 1
        self.progress.grid(column=0, row=row, columnspan=3, sticky='we', pady=2)  # noqa: E501

    def show_advanced_install_button(self):
        self.app_install_advanced.grid(column=2, row=0, sticky='w', pady=2)


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_visible = False
        self.tooltip_window = None

        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if not self.tooltip_visible:
            x, y, _, _ = self.widget.bbox("insert")
            x += self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - 200  # noqa: E501
            y += self.widget.winfo_rooty() - 25

            self.tooltip_window = Toplevel(self.widget)
            self.tooltip_window.wm_overrideredirect(True)
            self.tooltip_window.wm_geometry(f"+{x}+{y}")

            label = Label(
                self.tooltip_window,
                text=self.text,
                justify="left",
                background="#eeeeee",
                relief="solid",
                padding=4,
                borderwidth=1,
                foreground="#000000",
                wraplength=192
            )
            label.pack(ipadx=1)

            self.tooltip_visible = True

    def hide_tooltip(self, event=None):
        if self.tooltip_visible:
            self.tooltip_visible = False
        if self.tooltip_window:
            self.tooltip_window.destroy()


class PromptGui(Frame):
    def __init__(self, root, title="", prompt="", **kwargs):
        super(PromptGui, self).__init__(root, **kwargs)
        self.options = {"title": title, "prompt": prompt}
        if title is not None:
            self.options['title'] = title
        if prompt is not None:
            self.options['prompt'] = prompt
        self.root = root

    def draw_prompt(self):
        text = "Store Password"
        store_button = Button(
            self.root,
            text=text,
            command=lambda: input_prompt(self.root, text, self.options)
        )
        store_button.pack(pady=20)


def show_error(message, fatal=True, detail=None, app=None, parent=None):  # noqa: E501
    title = "Error"
    if fatal:
        title = "Fatal Error"

    kwargs = {'message': message}
    if parent and hasattr(app, parent):
        kwargs['parent'] = app.__dict__.get(parent)
    if detail:
        kwargs['detail'] = detail
    messagebox.showerror(title, **kwargs)
    if fatal and hasattr(app, 'root'):
        app.root.destroy()


def ask_question(question, secondary):
    return messagebox.askquestion(question, secondary)


def input_prompt(root, title, prompt):
    # Prompt for the password
    input = simpledialog.askstring(title, prompt, show='*', parent=root)
    return input
