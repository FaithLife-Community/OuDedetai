import curses
import logging
from typing import Optional
try:
    from dialog import Dialog #type: ignore[import-untyped]
except ImportError:
    pass



def text(screen, text, height=None, width=None, title=None, backtitle=None, colors=True):
    dialog = Dialog()
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle
    dialog.infobox(text, **options)


def progress_bar(screen, text, percent, height=None, width=None, title=None, backtitle=None, colors=True):
    screen.dialog = Dialog()
    screen.dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle

    screen.dialog.gauge_start(text=text, percent=percent, **options)


#FIXME: Not working. See tui_screen.py#262.
def update_progress_bar(screen, percent, text='', update_text=False):
    screen.dialog.autowidgetsize = True
    screen.dialog.gauge_update(percent, text, update_text)


def stop_progress_bar(screen):
    screen.dialog.autowidgetsize = True
    screen.dialog.gauge_stop()


def tasklist_progress_bar(
    screen,
    text,
    percent,
    elements,
    height=None,
    width=None,
    title=None,
    backtitle=None,
    colors=None
):
    dialog = Dialog()
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle

    if elements is None:
        elements = {}

    elements_list = [(k, v) for k, v in elements.items()]
    try:
        dialog.mixedgauge(text=text, percent=percent, elements=elements_list, **options)
    except Exception as e:
        logging.debug(f"Error in mixedgauge: {e}")
        raise


def input(screen, question_text, height=None, width=None, init="",  title=None, backtitle=None, colors=True):
    dialog = Dialog()
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle
    code, input = dialog.inputbox(question_text, init=init, **options)
    return code, input


def password(screen, question_text, height=None, width=None, init="",  title=None, backtitle=None, colors=True):
    dialog = Dialog()
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle
    code, password = dialog.passwordbox(question_text, init=init, insecure=True, **options)
    return code, password


def confirm(screen, question_text, yes_label="Yes", no_label="No",
            height=None, width=None, title=None, backtitle=None, colors=True):
    dialog = Dialog()
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle
    check = dialog.yesno(question_text, height, width, yes_label=yes_label, no_label=no_label, **options)
    return check  # Returns "ok" or "cancel"


def directory_picker(
    screen,
    path_dir,
    height=None,
    width=None,
    title=None,
    backtitle=None,
    colors=True
) -> Optional[str]:
    str_dir = str(path_dir)

    path = None
    try:
        dialog = Dialog()
        dialog.autowidgetsize = True
        options = {'colors': colors}
        if height is not None:
            options['height'] = height
        if width is not None:
            options['width'] = width
        if title is not None:
            options['title'] = title
        if backtitle is not None:
            options['backtitle'] = backtitle
        curses.curs_set(1)
        _, raw_path = dialog.dselect(str_dir, **options)
        path = str(raw_path)
        curses.curs_set(0)
    except Exception as e:
        logging.error("An error occurred:", e)
        curses.endwin()

    return path


def menu(
    screen,
    question_text,
    choices,
    height=None,
    width=None,
    menu_height=8,
    title=None,
    backtitle=None,
    colors=True
):
    tag_to_description = {tag: description for tag, description in choices}
    dialog = Dialog(dialog="dialog")
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle

    menu_options = [(tag, description) for i, (tag, description) in enumerate(choices)]
    code, tag = dialog.menu(question_text, height, width, menu_height, menu_options, **options)
    selected_description = tag_to_description.get(tag)

    if code == dialog.OK:
        return code, tag, selected_description
    elif code == dialog.CANCEL:
        return None, None, "Return to Main Menu"


def buildlist(
    screen,
    text,
    items=[],
    height=None,
    width=None,
    list_height=None,
    title=None,
    backtitle=None,
    colors=True
):
    # items is an interable of (tag, item, status)
    dialog = Dialog(dialog="dialog")
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle

    code, tags = dialog.buildlist(text, list_height=list_height, items=items, **options)

    if code == dialog.OK:
        return code, tags
    elif code == dialog.CANCEL:
        return None


def checklist(
    screen,
    text,
    items=[],
    height=None,
    width=None,
    list_height=None,
    title=None,
    backtitle=None,
    colors=True
):
    # items is an iterable of (tag, item, status)
    dialog = Dialog(dialog="dialog")
    dialog.autowidgetsize = True
    options = {'colors': colors}
    if height is not None:
        options['height'] = height
    if width is not None:
        options['width'] = width
    if title is not None:
        options['title'] = title
    if backtitle is not None:
        options['backtitle'] = backtitle

    code, tags = dialog.checklist(text, choices=items, list_height=list_height, **options)

    if code == dialog.OK:
        return code, tags
    elif code == dialog.Cancel:
        return None
