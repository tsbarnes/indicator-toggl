#!/usr/bin/env python
"""
indicator-toggl.py

Copyright (c) 2014 D. Robert Adams. All rights reserved.
Modified for toggl API v8 by Beau Raines
Module-ized by T. Scott Barnes

ASCII art from http://patorjk.com/software/taag/#p=display&c=bash&f=Standard
"""

import datetime
import optparse
import os
import sys
import signal

from gi.repository import GObject, Gtk, AppIndicator3, Notify

from pytoggl.utility import Singleton, Config, DateAndTime, Logger
from pytoggl.toggl import (
    ClientList, ProjectList, TimeEntry, TimeEntryList, User)

APP_ID = 'indicator-toggl'


class IndicatorToggl:
    """
    App Indicator for Toggl.
    """
    app_id = None
    app_indicator = None
    timer_dialog = None
    timer_entry = None
    project_liststore = None
    project_combo = None
    menu = None
    start_item = None
    stop_item = None
    quit_item = None

    def notify(self, message):
        """
        Displays a desktop notification.
        """
        notification = Notify.Notification.new('Toggl', message,
                                               'toggldesktop')
        notification.show()

    def update(self, data=None):
        """
        Updates time entry list from Toggl and sets appindicator status
        for if a timer is running.
        """
        TimeEntryList().reload()
        entry = TimeEntryList().now()

        if entry is None:
            self.app_indicator.set_status(
                AppIndicator3.IndicatorStatus.ACTIVE)
            self.start_item.show()
            self.stop_item.hide()
        else:
            self.app_indicator.set_status(
                AppIndicator3.IndicatorStatus.ATTENTION)
            self.start_item.hide()
            self.stop_item.show()

        return True

    def start_timer(self, widget, data=None):
        """
        Start a timer.
        """
        response = self.timer_dialog.run()
        self.timer_dialog.hide()

        if response == Gtk.ResponseType.OK:
            project_iter = self.project_combo.get_active_iter()
            entry = TimeEntry(description=self.timer_entry.get_text())
            if project_iter is not None:
                project_model = self.project_combo.get_model()
                entry.set('project', project_model[project_iter][0])
            entry.start()
            self.app_indicator.set_status(
                AppIndicator3.IndicatorStatus.ATTENTION)
            self.start_item.hide()
            self.stop_item.show()
            friendly_time = DateAndTime().format_time(
                DateAndTime().parse_iso_str(entry.get('start')))
            self.notify('%s started at %s' % (entry.get('description'),
                                              friendly_time))

    def stop_timer(self, widget, data=None):
        """
        Stop the toggl timer, if running.
        """
        entry = TimeEntryList().now()

        if entry is not None:
            entry.stop()

            Logger.debug(entry.json())
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.start_item.show()
            self.stop_item.hide()
            friendly_time = DateAndTime().format_time(
                DateAndTime().parse_iso_str(entry.get('stop')))
            self.notify('%s stopped at %s' % (entry.get('description'),
                                              friendly_time))
        else:
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.start_item.show()
            self.stop_item.hide()
            self.notify("You're not working on anything right now.")

    def quit(self, widget, data=None):
        """
        Quit the app.
        """
        Notify.uninit()
        Gtk.main_quit()

    def __init__(self, app_id):
        """
        Initialize UI elements.
        """
        self.app_id = app_id
        Notify.init(app_id)
        self.app_indicator = AppIndicator3.Indicator.new(
            app_id, 'toggl_stopped',
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.app_indicator.set_attention_icon('toggl_running')

        self.timer_dialog = Gtk.Dialog(
            'Toggl Timer', None, Gtk.DialogFlags.MODAL,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OK, Gtk.ResponseType.OK))
        timer_label = Gtk.Label('What are you working on?')
        self.timer_dialog.vbox.pack_start(timer_label, False, False, 0)
        timer_label.show()
        self.timer_entry = Gtk.Entry()
        self.timer_dialog.vbox.pack_start(self.timer_entry, True, True, 0)
        self.timer_entry.show()

        self.project_liststore = Gtk.ListStore(int, str)
        for project in ProjectList():
            self.project_liststore.append([project['id'], project['name']])

        self.project_combo = Gtk.ComboBox.new_with_model(
            self.project_liststore)
        renderer_text = Gtk.CellRendererText()
        self.project_combo.pack_start(renderer_text, True)
        self.project_combo.add_attribute(renderer_text, "text", 1)
        self.timer_dialog.vbox.pack_start(self.project_combo, False, False, 0)
        self.project_combo.show()

        self.menu = Gtk.Menu()
        self.app_indicator.set_menu(self.menu)

        self.start_item = Gtk.MenuItem('Start Timer')
        self.menu.append(self.start_item)
        self.start_item.show()
        self.start_item.connect('activate', self.start_timer)

        self.stop_item = Gtk.MenuItem('Stop Timer')
        self.menu.append(self.stop_item)
        self.stop_item.show()
        self.stop_item.connect('activate', self.stop_timer)

        self.quit_item = Gtk.MenuItem('Quit')
        self.menu.append(self.quit_item)
        self.quit_item.show()
        self.quit_item.connect('activate', self.quit)

        GObject.timeout_add(500, self.update)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = IndicatorToggl(APP_ID)
    Gtk.main()
    sys.exit(0)
