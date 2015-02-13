#!/usr/bin/python
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
from pytoggl.toggl import ClientList, ProjectList, TimeEntry, TimeEntryList, User

APP_ID = 'indicator-toggl'

#############################################################################
#     ____                                          _   _     _
#    / ___|___  _ __ ___  _ __ ___   __ _ _ __   __| | | |   (_)_ __   ___
#   | |   / _ \| '_ ` _ \| '_ ` _ \ / _` | '_ \ / _` | | |   | | '_ \ / _ \
#   | |__| (_) | | | | | | | | | | | (_| | | | | (_| | | |___| | | | |  __/
#    \____\___/|_| |_| |_|_| |_| |_|\__,_|_| |_|\__,_| |_____|_|_| |_|\___|
#
#############################################################################

#----------------------------------------------------------------------------
# CLI
#----------------------------------------------------------------------------
class CLI(object):
    """
    Singleton class to process command-line actions.
    """
    __metaclass__ = Singleton

    def __init__(self):
        """
        Initializes the command-line parser and handles the command-line
        options.
        """

        # Override the option parser epilog formatting rule.
        # See http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output
        optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog

        self.parser = optparse.OptionParser(usage="Usage: %prog [OPTIONS] [ACTION]", \
            epilog="\nActions:\n"
            "  add DESCR [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)\n\tcreates a completed time entry\n"
            "  clients\n\tlists all clients\n"
            "  continue DESCR\n\trestarts the given entry\n"
            "  ls\n\tlist recent time entries\n"
            "  now\n\tprint what you're working on now\n"
            "  projects\n\tlists all projects\n"
            "  rm ID\n\tdelete a time entry by id\n"
            "  start DESCR [@PROJECT] [DATETIME]\n\tstarts a new entry\n"
            "  stop [DATETIME]\n\tstops the current entry\n"
            "  www\n\tvisits toggl.com\n"
            "\n"
            "  DURATION = [[Hours:]Minutes:]Seconds\n")
        self.parser.add_option("-q", "--quiet",
                              action="store_true", dest="quiet", default=False,
                              help="don't print anything")
        self.parser.add_option("-v", "--verbose",
                              action="store_true", dest="verbose", default=False,
                              help="print additional info")
        self.parser.add_option("-d", "--debug",
                              action="store_true", dest="debug", default=False,
                              help="print debugging output")

        # self.args stores the remaining command line args.
        (options, self.args) = self.parser.parse_args()

        # Process command-line options.
        Logger.level = Logger.INFO
        if options.quiet:
            Logger.level = Logger.NONE
        if options.debug:
            Logger.level = Logger.DEBUG
        if options.verbose:
            global VERBOSE
            VERBOSE = True

    def _add_time_entry(self, args):
        """
        Creates a completed time entry.
        args should be: DESCR [@PROJECT] START_DATE_TIME
            'd'DURATION | STOP_DATE_TIME
        """
        # Process the args.
        description = self._get_str_arg(args)

        project_name = self._get_project_arg(args, optional=True)
        if project_name is not None:
            project = ProjectList().find_by_name(project_name)
            if project == None:
                raise RuntimeError("Project '%s' not found." % project_name)

        start_time = self._get_datetime_arg(args, optional=False)
        duration = self._get_duration_arg(args, optional=True)
        if duration is None:
            stop_time = self._get_datetime_arg(args, optional=False)
            duration = (stop_time - start_time).total_seconds()
        else:
            stop_time = None

        # Create a time entry.
        entry = TimeEntry(
            description=description,
            start_time=start_time,
            stop_time=stop_time,
            duration=duration,
            project_name=project_name
        )

        Logger.debug(entry.json())
        entry.add()
        Logger.info('%s added' % description)

    def act(self):
        """
        Performs the actions described by the list of arguments in self.args.
        """
        if len(self.args) == 0 or self.args[0] == "ls":
            Logger.info(TimeEntryList())
        elif self.args[0] == "add":
            self._add_time_entry(self.args[1:])
        elif self.args[0] == "clients":
            print ClientList()
        elif self.args[0] == "continue":
            self._continue_entry(self.args[1:])
        elif self.args[0] == "now":
            self._list_current_time_entry()
        elif self.args[0] == "projects":
            print ProjectList()
        elif self.args[0] == "rm":
            self._delete_time_entry(self.args[1:])
        elif self.args[0] == "start":
            self._start_time_entry(self.args[1:])
        elif self.args[0] == "stop":
            self._stop_time_entry(self.args[1:])
        elif self.args[0] == "www":
            os.system(VISIT_WWW_COMMAND)
        else:
            self.print_help()

    def _continue_entry(self, args):
        """
        Continues a time entry. args[0] should be the description of the entry
        to restart. If a description appears multiple times in your history,
        then we restart the newest one.
        """
        if len(args) == 0:
            CLI().print_help()
        entry = TimeEntryList().find_by_description(args[0])
        if entry:
            entry.continue_entry()
            Logger.info("%s continued at %s" % (entry.get('description'),
                DateAndTime().format_time(datetime.datetime.now())))
        else:
            Logger.info("Did not find '%s' in list of entries." % args[0] )

    def _delete_time_entry(self, args):
        """
        Removes a time entry from toggl.
        args must be [ID] where ID is the unique identifier for the time
        entry to be deleted.
        """
        if len(args) == 0:
            CLI().print_help()

        entry_id = args[0]

        for entry in TimeEntryList():
            if entry.get('id') == int(entry_id):
                entry.delete()
                Logger.info("Deleting entry " + entry_id)

    def _get_datetime_arg(self, args, optional=False):
        """
        Returns args[0] as a localized datetime object, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        else:
            return DateAndTime().parse_local_datetime_str(args.pop(0))

    def _get_duration_arg(self, args, optional=False):
        """
        Returns args[0] (e.g. 'dHH:MM:SS') as an integer number of
        seconds, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        elif args[0][0] != 'd':
            if optional:
                return None
            else:
                self.print_help()
        else:
            return DateAndTime().duration_str_to_seconds( args.pop(0)[1:] )

    def _get_project_arg(self, args, optional=False):
        """
        If the first entry in args is a project name (e.g., '@project')
        then return the name of the project, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        elif args[0][0] != '@':
            if optional:
                return None
            else:
                self.print_help()
        else:
            return args.pop(0)[1:]

    def _get_str_arg(self, args, optional=False):
        """
        Returns the first entry in args as a string, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        else:
            return args.pop(0)

    def _list_current_time_entry(self):
        """
        Shows what the user is currently working on.
        """
        entry = TimeEntryList().now()

        if entry != None:
            Logger.info(str(entry))
        else:
            Logger.info("You're not working on anything right now.")

    def print_help(self):
        """Prints the usage message and exits."""
        self.parser.print_help()
        sys.exit(1)

    def _start_time_entry(self, args):
        """
        Starts a new time entry.
        args should be: DESCR [@PROJECT] [DATETIME]
        """
        description = self._get_str_arg(args, optional=False)
        project_name = self._get_project_arg(args, optional=True)
        start_time = self._get_datetime_arg(args, optional=True)

        # Create the time entry.
        entry = TimeEntry(
            description=description,
            start_time=start_time,
            project_name=project_name
        )
        entry.start()
        Logger.debug(entry.json())
        friendly_time = DateAndTime().format_time(DateAndTime().parse_iso_str(entry.get('start')))
        Logger.info('%s started at %s' % (description, friendly_time))

    def _stop_time_entry(self, args):
        """
        Stops the current time entry.
        args contains an optional end time.
        """

        entry = TimeEntryList().now()
        if entry != None:
            if len(args) > 0:
                entry.stop(DateAndTime().parse_local_datetime_str(args[0]))
            else:
                entry.stop()

            Logger.debug(entry.json())
            friendly_time = DateAndTime().format_time(DateAndTime().parse_iso_str(entry.get('stop')))
            Logger.info('%s stopped at %s' % (entry.get('description'), friendly_time))
        else:
            Logger.info("You're not working on anything right now.")

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
        notification = Notify.Notification.new('Toggl', message, 'toggldesktop')
        notification.show()

    def update(self, data=None):
        """
        Updates time entry list from Toggl and sets appindicator status
        for if a timer is running.
        """
        TimeEntryList().reload()
        entry = TimeEntryList().now()

        if entry == None:
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        else:
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ATTENTION)

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
            if project_iter != None:
                project_model = self.project_combo.get_model()
                entry.set('project', project_model[project_iter][0])
            entry.start()
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ATTENTION)
            friendly_time = DateAndTime().format_time(DateAndTime().parse_iso_str(entry.get('start')))
            self.notify('%s started at %s' % (entry.get('description'), friendly_time))

    def stop_timer(self, widget, data=None):
        """
        Stop the toggl timer, if running.
        """
        entry = TimeEntryList().now()

        if entry != None:
            entry.stop()

            Logger.debug(entry.json())
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            friendly_time = DateAndTime().format_time(DateAndTime().parse_iso_str(entry.get('stop')))
            self.notify('%s stopped at %s' % (entry.get('description'), friendly_time))
        else:
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
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
        self.app_indicator = AppIndicator3.Indicator.new(app_id, 'toggl_stopped', AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.app_indicator.set_attention_icon('toggl_running')

        self.timer_dialog = Gtk.Dialog('Toggl Timer', None, Gtk.DialogFlags.MODAL, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK))
        timer_label = Gtk.Label('What are you working on?')
        self.timer_dialog.vbox.pack_start(timer_label, False, False, 0)
        timer_label.show()
        self.timer_entry = Gtk.Entry()
        self.timer_dialog.vbox.pack_start(self.timer_entry, True, True, 0)
        self.timer_entry.show()

        self.project_liststore = Gtk.ListStore(int, str)
        for project in ProjectList():
            self.project_liststore.append([project['id'], project['name']])

        self.project_combo = Gtk.ComboBox.new_with_model(self.project_liststore)
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
