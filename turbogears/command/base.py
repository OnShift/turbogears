"""Commands for the TurboGears command line tool."""

import optparse
import sys
import os
import os.path
import glob

import pkg_resources
import dispatch

import configobj

import turbogears
from turbogears.util import get_model, load_project_config, \
        get_project_config, get_package_name
from turbogears.identity import SecureObject, from_any_host
from turbogears import config, database
from sacommand import sacommand

sys.path.insert(0, os.getcwd())

no_connection_param = ["help", "list"]
no_model_param = ["help"]


def silent_os_remove(fname):
    """Try to remove file 'fname' but mute any error that may happen.

    Returns True if file was actually removed and False otherwise.

    """
    try:
        os.remove(fname)
        return True
    except os.error:
        pass
    return False


class CommandWithDB(object):
    """Base class for commands that need to use the database"""

    config = None

    def __init__(self, version):
        pass

    def find_config(self):
        """Chooses the config file, trying to guess whether this is a
        development or installed project."""
        load_project_config(self.config)
        self.dburi = config.get("sqlobject.dburi", None)
        if self.dburi and self.dburi.startswith("notrans_"):
            self.dburi = self.dburi[8:]


class SQL(CommandWithDB):
    """Wrapper command for sqlobject-admin, and some sqlalchemy support.

    This automatically supplies sqlobject-admin with the database that
    is found in the config file.

    Will also supply the model module as appropriate.

    """

    desc = "Run the database provider manager"
    need_project = True

    def __init__(self, version):
        if len(sys.argv) == 1 or sys.argv[1][0] == "-":
            parser = optparse.OptionParser(
                usage="%prog sql [command]\n\n" \
                      "hint: '%prog sql help' will list the sqlobject " \
                      "commands",
                version="%prog " + version)
            parser.add_option("-c", "--config", help="config file",
                              dest="config")
            options, args = parser.parse_args(sys.argv[1:3])

            if not options.config:
                parser.error("Please provide a valid option or command.")
            self.config = options.config
            # get rid of our config option
            if args:
                del sys.argv[1]
            else:
                del sys.argv[1:3]

        self.find_config()

    def run(self):
        """Executes the sqlobject-admin code."""
        if not "--egg" in sys.argv and not turbogears.util.get_project_name():
            print "This don't look like a TurboGears project."
            return
        else:
            command = sys.argv[1]

            if config.get("sqlalchemy.dburi"):
                try:
                    sacommand(command, sys.argv)
                except dispatch.interfaces.NoApplicableMethods:
                    sacommand("help", [])
                return

            try:
                from sqlobject.manager import command as socommand
            except ImportError:
                print "Error: SQLObject not installed."
                return

            if command not in no_connection_param:
                if self.dburi:
                    print "Using database URI %s" % self.dburi
                    sys.argv.insert(2, self.dburi)
                    sys.argv.insert(2, "-c")
                else:
                    print ("Database URI not specified in the config file"
                        " (%s).\nPlease be sure it's on the command line."
                            % (self.config or get_project_config()))

            if command not in no_model_param:
                if not "--egg" in sys.argv:
                    eggname = glob.glob("*.egg-info")
                    if not eggname or not os.path.exists(
                            os.path.join(eggname[0], "sqlobject.txt")):
                        eggname = self.fix_egginfo(eggname)
                    eggname = eggname[0].replace(".egg-info", "")
                    if not "." in sys.path:
                        sys.path.append(".")
                        pkg_resources.working_set.add_entry(".")
                    sys.argv.insert(2, eggname)
                    sys.argv.insert(2, "--egg")

            socommand.the_runner.run(sys.argv)

    def fix_egginfo(self, eggname):
        """Add egg-info directory if necessary."""
        print """
This project seems incomplete. In order to use the sqlobject commands
without manually specifying a model, there needs to be an
egg-info directory with an appropriate sqlobject.txt file.

I can fix this automatically. Would you like me to?
"""
        dofix = raw_input("Enter [y] or n: ")
        if not dofix or dofix.lower()[0] == 'y':
            oldargs = sys.argv
            sys.argv = ["setup.py", "egg_info"]
            import imp
            imp.load_module("setup", *imp.find_module("setup", ["."]))
            sys.argv = oldargs

            import setuptools
            package = setuptools.find_packages()[0]
            eggname = glob.glob("*.egg-info")
            sqlobjectmeta = open(os.path.join(eggname[0], "sqlobject.txt"), "w")
            sqlobjectmeta.write("""db_module=%(package)s.model
history_dir=$base/%(package)s/sqlobject-history
""" % dict(package=package))
        else:
            sys.exit(0)
        return eggname


class Shell(CommandWithDB):
    """Convenient version of the Python interactive shell.

    This shell attempts to locate your configuration file and model module
    so that it can import everything from your model and make it available
    in the Python shell namespace.

    """

    desc = "Start a Python prompt with your database available"
    need_project = True

    def run(self):
        """Run the shell"""
        self.find_config()

        mod = get_model()
        if mod:
            locals = mod.__dict__
        else:
            locals = dict(__name__="tg-admin")

        if config.get("sqlalchemy.dburi"):
            using_sqlalchemy = True
            database.get_engine()
            locals.update(dict(session=database.session,
                metadata=database.metadata))
        else:
            using_sqlalchemy = False

        try:
            # try to use IPython if possible
            from IPython.terminal.interactiveshell import TerminalInteractiveShell

            class CustomIPShell(TerminalInteractiveShell):
                def raw_input(self, *args, **kw):
                    try:
                        return TerminalInteractiveShell.raw_input(self,
                            *args, **kw) # needs decoding (see below)?
                    except EOFError:
                        r = raw_input("Do you wish to commit your "
                                    "database changes? [yes]")
                        if not r.lower().startswith("n"):
                            if using_sqlalchemy:
                                self.push("session.flush()")
                            else:
                                self.push("hub.commit()")
                        raise EOFError

            shell = CustomIPShell(user_ns=locals)
            shell.mainloop()
        except ImportError:
            import code

            class CustomShell(code.InteractiveConsole):
                def raw_input(self, *args, **kw):
                    try:
                        import readline
                    except ImportError:
                        pass
                    try:
                        r = code.InteractiveConsole.raw_input(self,
                            *args, **kw)
                        for encoding in (getattr(sys.stdin, 'encoding', None),
                                sys.getdefaultencoding(), 'utf-8', 'latin-1'):
                            if encoding:
                                try:
                                    return r.decode(encoding)
                                except UnicodeError:
                                    pass
                        return r
                    except EOFError:
                        r = raw_input("Do you wish to commit your "
                                      "database changes? [yes]")
                        if not r.lower().startswith("n"):
                            if using_sqlalchemy:
                                self.push("session.flush()")
                            else:
                                self.push("hub.commit()")
                        raise EOFError

            shell = CustomShell(locals=locals)
            shell.interact()


class ToolboxCommand(CommandWithDB):

    desc = "Launch the TurboGears Toolbox"

    def __init__(self, version):
        self.hostlist = ['127.0.0.1', '::1', '::ffff:127.0.0.1']

        parser = optparse.OptionParser(
            usage="%prog toolbox [options]",
            version="%prog " + version)
        parser.add_option("-n", "--no-open",
            help="don't open browser automatically",
            dest="noopen", action="store_true", default=False)
        parser.add_option("-c", "--add-client",
            help="allow client ip address specified to connect to toolbox"
                " (can be specified more than once)",
            dest="host", action="append", default=None)
        parser.add_option("-p", "--port",
            help="port to run the Toolbox on",
            dest="port", default=7654)
        parser.add_option("--config",
            help="config file", dest="config",
            default=self.config or get_project_config())

        options, args = parser.parse_args(sys.argv[1:])
        self.port = int(options.port)
        self.noopen = options.noopen
        self.config = options.config

        if options.host:
            self.hostlist = self.hostlist + options.host

        turbogears.widgets.load_widgets()

    def openbrowser(self):
        import webbrowser
        webbrowser.open("http://localhost:%d" % self.port)

    def run(self):
        import cherrypy
        from turbogears import toolbox

        # Make sure we have full configuration with every option
        # in it so other plugins or whatever find what they need
        # when starting even inside the toolblox
        conf = get_package_name()
        conf = conf and "%s.config" % conf or None
        conf = config.config_obj(configfile=self.config, modulename=conf)

        if 'global' in conf:
            config.update({'global': conf['global']})

        root = SecureObject(toolbox.Toolbox(), from_any_host(self.hostlist),
                exclude=['noaccess'])

        cherrypy.tree.mount(root, "/")

        # amend some parameters since we are running from the command
        # line in order to change port, log methods...
        config.update({'global': {
            'server.socket_port': self.port,
            'server.webpath': '/',
            'server.environment': 'development',
            'server.log_to_screen': True,
            'autoreload.on': False,
            'server.package': 'turbogears.toolbox',
            'log_debug_info_filter.on': False,
            'identity.failure_url': '/noaccess',
            'identity.force_external_redirect': False,
            'tg.defaultview': 'kid',
            'tg.strict_parameters': False,
            'kid.outputformat': 'html default',
            'kid.encoding': 'utf-8'
            }})

        if not self.noopen:
            cherrypy.server.start_with_callback(self.openbrowser)
        else:
            cherrypy.server.start()


commands = None

def main():
    """Main command runner. Manages the primary command line arguments."""
    # add commands defined by entrypoints
    commands = {}
    for entrypoint in pkg_resources.iter_entry_points("turbogears.command"):
        command = entrypoint.load()
        commands[entrypoint.name] = (command.desc, entrypoint)

    def _help():
        """Custom help text for tg-admin."""

        print """
TurboGears %s command line interface

Usage: %s [options] <command>

Options:
    -c CONFIG --config=CONFIG    Config file to use
    -e EGG_SPEC --egg=EGG_SPEC   Run command on given Egg

Commands:""" % (turbogears.__version__, sys.argv[0])

        longest = max([len(key) for key in commands.keys()])
        format = "%" + str(longest) + "s  %s"
        commandlist = commands.keys()
        commandlist.sort()
        for key in commandlist:
            print format % (key, commands[key][0])

    parser = optparse.OptionParser()
    parser.allow_interspersed_args = False
    parser.add_option("-c", "--config", dest="config")
    parser.add_option("-e", "--egg", dest="egg")
    parser.print_help = _help
    options, args = parser.parse_args(sys.argv[1:])

    # if command is not found display help
    if not args or not commands.has_key(args[0]):
        _help()
        sys.exit()

    commandname = args[0]
    # strip command and any global options from the sys.argv
    sys.argv = [sys.argv[0]] + args[1:]
    command = commands[commandname][1]
    command = command.load()

    if options.egg:
        egg = pkg_resources.get_distribution(options.egg)
        os.chdir(egg.location)

    if hasattr(command,"need_project"):
        if not turbogears.util.get_project_name():
            print "This command needs to be run from inside a project directory"
            return
        elif not options.config and not os.path.isfile(get_project_config()):
            print """No default config file was found.
If it has been renamed use:
tg-admin --config=<FILE> %s""" % commandname
            return
    command.config = options.config
    command = command(turbogears.__version__)
    command.run()


__all__ = ["main"]
