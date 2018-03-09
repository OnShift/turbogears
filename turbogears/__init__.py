"TurboGears Front-to-Back Web Framework"

import warnings

import pkg_resources

from turbogears import config
from turbogears.controllers import expose, flash, validate, redirect, \
                                   error_handler, exception_handler, url
from turbogears import controllers, view, database, validators, command, \
                       i18n, widgets, startup, scheduler
from turbogears.release import version as __version__, author as __author__, \
                               email as __email__, license as __license__, \
                               copyright as __copyright__
from turbogears.widgets import mochikit
from turbogears.widgets import jsi18nwidget
from turbogears.config import update_config
from turbogears.paginate import paginate

from turbogears.startup import start_server

# load global symbols for TG extensions (currently only used by tgfastdata)
extensions = pkg_resources.iter_entry_points("turbogears.extensions")
for entrypoint in extensions:
    try:
        extension = entrypoint.load()
        if hasattr(extension, "tgsymbols"):
            globals().update(extension.tgsymbols())
    except Exception, exception:
        warnings.warn("Could not load extension %s from %s: %s"
            % (entrypoint, entrypoint.dist, exception), stacklevel=2)

i18n.install() # adds _ (gettext) to builtins namespace

IMPORT_THIS_TO_EXCLUDE_PACKAGE_FROM_MEMORY_PROFILING = True

__all__ = ["url", "expose", "redirect", "validate", "flash",
           "error_handler", "exception_handler",
           "view", "controllers", "update_config",
           "database", "command", "validators", "mochikit", "widgets",
           "config", "start_server", "scheduler"]
