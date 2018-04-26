import logging
import os
import sys
import json
import threading
import tempfile
from fluent import handler
from memory_profiler import memory_usage
from pympler import summary, muppy
from enum import Enum
from collections import namedtuple
from pympler_setup_helper import _is_pympler_profiling_value_on, _set_pympler_profiling_value, pympler_end_points
from sqlobject.cache import CacheFactory

MemoryProfilerStateItem = namedtuple('MemoryProfilerStateItem', ['id', 'command', 'profiling_status'])

class MemoryProfilerState(Enum):
    UNKNOWN = MemoryProfilerStateItem(id=-1, command='', profiling_status=None)
    OFF = MemoryProfilerStateItem(id=0, command='off', profiling_status=False)
    ON = MemoryProfilerStateItem(id=1, command='on', profiling_status=True)
    ECHO = MemoryProfilerStateItem(id=2, command='echo', profiling_status=None)
    PYMPLER = MemoryProfilerStateItem(id=3, command='pympler', profiling_status=None)
    CACHE = MemoryProfilerStateItem(id=4, command='cache', profiling_status=None)
    DEBUG = MemoryProfilerStateItem(id=5, command='debug', profiling_status=None)

# memory profiler system configuration
FLUENTD_HOST_NAME = os.environ.get('FLUENTD_HOST_NAME', 'fluentd')
_fluentd_port_str = os.environ.get('FLUENTD_PORT', '24224')
FLUENTD_PORT = int(_fluentd_port_str) if _fluentd_port_str.isdigit() else 24224
TURBOGEARS_PROFILER_FIFO_PATH = os.environ.get('TURBOGEARS_PROFILER_FIFO_PATH',
                                               '{}/turbogears_memory_profiler'.format(tempfile.gettempdir()))
TURBOGEARS_PROFILER_FIFO_NAME = os.environ.get('TURBOGEARS_PROFILER_FIFO_NAME', 'turbogears_memory_config_fifo_{}')
TURBOGEARS_PROFILER_LOG_TO_CONSOLE = os.environ.get('TURBOGEARS_PROFILER_LOG_TO_CONSOLE', 'False') == 'True'

# setup thread log handler to monitor state of memory profile logging
thread_log = logging.getLogger("memory_profiler_thread_log")
thread_log_hdlr = logging.StreamHandler(sys.stdout)
thread_log_hdlr.setLevel(logging.INFO)
thread_log.addHandler(thread_log_hdlr)
thread_log.setLevel(logging.INFO)

# set up memory profiler log handler to feed memory profiler output into fluentd
memory_log = logging.getLogger("memory_profiler")
if TURBOGEARS_PROFILER_LOG_TO_CONSOLE:
    mem_out_hdlr = logging.StreamHandler(sys.stdout)
    mem_out_hdlr.setLevel(logging.INFO)
    memory_log.addHandler(mem_out_hdlr)

fluentd_format = {
    'hostname': '%(hostname)s',
    'where': '%(controller_module)s.%(controller_class)s.%(endpoint)s'
}

mem_fluent_hdlr = handler.FluentHandler('turbogears.memory_profiler', host=FLUENTD_HOST_NAME, port=FLUENTD_PORT)
mem_fluentd_formatter = handler.FluentRecordFormatter(fluentd_format)
mem_fluent_hdlr.setFormatter(mem_fluentd_formatter)
mem_fluent_hdlr.setLevel(logging.INFO)
memory_log.addHandler(mem_fluent_hdlr)

memory_log.setLevel(logging.INFO)

thread_log.info('turbogears memory profiler settings: FLUENTD_HOST_NAME={} FLUENTD_PORT={} '
                'TURBOGEARS_PROFILER_FIFO_PATH={} '
                'TURBOGEARS_PROFILER_FIFO_NAME={} '
                'TURBOGEARS_PROFILER_LOG_TO_CONSOLE={}'.format(FLUENTD_HOST_NAME,FLUENTD_PORT,
                                                               TURBOGEARS_PROFILER_FIFO_PATH,
                                                               TURBOGEARS_PROFILER_FIFO_NAME,
                                                               TURBOGEARS_PROFILER_LOG_TO_CONSOLE)
                )




def toggle_memory_profile_via_fifo(_thread_log):
    """
    Execution body of a thread that monitors any input on a named pipe located at 
    /tmp/turbogears_memory_profiler/turbogears_memory_config_fifo_{pid}.
    Accepts string value of 'ON', 'OFF' or 'ECHO' with new line via named pipe. 'ON' turns on memory profiling , 
    'OFF' turns off memory profiling, 'ECHO' publishes current value of the variable to the log
    :param _thread_log: console logger
    :return: 
    """
    _thread_log.info('started toggle_memory_profile_via_fifo thread PID({})'.format(os.getpid()))
    fifo_path = TURBOGEARS_PROFILER_FIFO_PATH
    if not os.path.exists(TURBOGEARS_PROFILER_FIFO_PATH):
        os.mkdir(fifo_path)
    fifo_name = os.path.join(TURBOGEARS_PROFILER_FIFO_PATH, TURBOGEARS_PROFILER_FIFO_NAME.format(os.getpid()))
    if not os.path.exists(fifo_name):
        _thread_log.info('[{}] creating FIFO {}'.format(os.getpid(), fifo_name))
        os.mkfifo(fifo_name)
    while True:
        with open(fifo_name, 'r') as config_fifo:
            _thread_log.info('opened FIFO {} in toggle_memory_profile_via_fifo thread'.format(fifo_name))
            _process_fifo_input(_thread_log, config_fifo)


def _process_fifo_input(_thread_log, config_fifo):
    """
    Pulls a command out of configuration FIFO and processes it into proper state and parameters
    :param _thread_log: console logger
    :param config_fifo: FIFO that transmits config commands to process
    :return: None
    """
    line = config_fifo.readline()[:-1]
    state, params = _get_state_from_pipe_command(line)
    _thread_log.info('READ LINE toggle_memory_profile_via_fifo thread ====>{}, state: {}'.format(line, state.name))
    if state == MemoryProfilerState.ON or state == MemoryProfilerState.OFF:
        set_memory_profile_logging(_thread_log, state.value.profiling_status)
    elif state == MemoryProfilerState.ECHO:
        _thread_log.info('ECHO MEMORY_PROFILE_LOGGING_ON ==> {}\nPYMPLER endpints: {}'.format(
            get_memory_profile_logging_on(), pympler_end_points))
    elif state == MemoryProfilerState.PYMPLER and get_memory_profile_logging_on():
        _thread_log.info('Setting PYMPLER tracking for {} ==> {}'.format(params['endpoint'],
                                                                         params['persistence']))
        _set_pympler_profiling_value(params['endpoint'], params['persistence'])
    elif state == MemoryProfilerState.CACHE:
        _publish_cache_size()
    elif state == MemoryProfilerState.DEBUG:
        _thread_log.info('---------- DEBUGGING PROCESS ({}) ----------'.format(os.getpid()))
        import rpdb
        rpdb.set_trace()
        _thread_log.info('---------- DEBUGGING COMPLETED ({}) ----------'.format(os.getpid()))


def _publish_cache_size():
    import gc
    cache_factories = [c for c in gc.get_objects() if isinstance(c, CacheFactory)]
    cached_objects = []
    for cf in cache_factories:
        cached_objects += cf.cache.values()
    co_dict = {}
    for co in cached_objects:
        class_name = type(co).__name__
        co_dict[class_name] = (class_name, 1, sys.getsizeof(co)) if class_name not in co_dict else \
            (class_name,  co_dict[class_name][1] + 1, co_dict[class_name][2] + sys.getsizeof(co))
    import operator
    co_list_sorted = sorted(co_dict.values(), key=operator.itemgetter(1), reverse=True)
    caches_summery_out = "Class Name\t|\tCount\t|\tSize\n"
    total_size = 0
    for co in co_list_sorted:
        caches_summery_out += "{}\t|\t{}\t|\t{} B\n".format(*co)
        total_size += co[2]

    # all_objects = muppy.get_objects()
    # caches = muppy.filter(all_objects, Type=CacheFactory)
    # size_list = [summary.getsizeof(s) for s in caches]
    # caches_summery = summary.summarize(caches)
    # caches_summery_formatted = summary.format_(caches_summery)
    # caches_summery_out = ''
    # classes = {}
    # for name in [t.__name__ for t in caches if isinstance(t, type)]:
    #     classes[name] = 1 if name not in classes else classes[name]+1
    # import operator
    # classes = ["{}({})".format(*x) for x in sorted(classes.items(), key=operator.itemgetter(1)) if x[1] > 2]
    # for s in caches_summery_formatted:
    #     caches_summery_out += s + '\n'
    thread_log.info("================ CACHED OBJECT SUMMARY ==============\n{}\n"
                    # "----------------------------------------------------\n{}"
                    "----------------------------------------------------\nTOTAL:\t{} KB".format(caches_summery_out,
                                                                                                 # '\t'.join(classes),
                                                                                                 total_size/1024))



def _get_state_from_pipe_command(command):
    """
    Process command string received from FIFO and if command is not known set it to UNKNOWN
    if command matches to command value MemoryProfilerState Enum return that enum with possible additional
    parameters
    :param command: string read in from FIFO
    :return: tuple State, Additional command parameters
    """
    command_values = command.split(' ')
    if command_values[0].lower() not in [MemoryProfilerState.ON.value.command,
                                         MemoryProfilerState.OFF.value.command,
                                         MemoryProfilerState.ECHO.value.command,
                                         MemoryProfilerState.PYMPLER.value.command,
                                         MemoryProfilerState.CACHE.value.command,
                                         MemoryProfilerState.DEBUG.value.command]:
        return MemoryProfilerState.UNKNOWN, None
    return {MemoryProfilerState.ON.value.command: (MemoryProfilerState.ON, None),
            MemoryProfilerState.OFF.value.command: (MemoryProfilerState.OFF, None),
            MemoryProfilerState.ECHO.value.command: (MemoryProfilerState.ECHO, None),
            MemoryProfilerState.PYMPLER.value.command: _parse_pympler_command(command_values),
            MemoryProfilerState.CACHE.value.command: (MemoryProfilerState.CACHE, None),
            MemoryProfilerState.DEBUG.value.command: (MemoryProfilerState.DEBUG, None)
            }[command_values[0].lower()]


def _parse_pympler_command(command_args):
    """
    parses special pympler command: extracts end point name and state of the end point 
    :param command_args: list of strings ['pympler','<python endpoint path>','<command value>']
    :return: either MemoryProfilerState.PYMPLER and command parameters or UNKNOWN in case of parsing failure
    """
    try:
        if len(command_args) == 3 and command_args[-1].lower() in ['on', 'once', 'off']:
            return (MemoryProfilerState.PYMPLER, {'endpoint': command_args[1],
                                                  'persistence': command_args[2]})
        return MemoryProfilerState.UNKNOWN, None
    except:
        return MemoryProfilerState.UNKNOWN, None


def create_config_thread(_thread_log):
    # start configuration pipe monitoring thread on import
    _config_thread = threading.Thread(target=toggle_memory_profile_via_fifo, args=(_thread_log,),
                                      name='toggle_memory_profile_via_fifo')
    _config_thread.setDaemon(True)
    _config_thread.start()
    return _config_thread

try:
    config_thread
except NameError:
    config_thread = create_config_thread(thread_log)


def get_memory_profile_logging_on():
    """
    Lazy loaded environment variable evaluated as a boolean
    :return: returns False if 'False' or absent, return True if set to 'True'
    """
    return os.environ.get('MEMORY_PROFILE_LOGGING_ON', 'False') == 'True'


def check_memory_profile_package_wide_disable(func):
    """
    Take a passed in function traverse to the package and check if it imports or contains
    a variable named IMPORT_THIS_TO_EXCLUDE_PACKAGE_FROM_MEMORY_PROFILING
    :param func: a function that is the base for package content search
    :return: True if variable is not declared or imported, False if it is included or imported or
            fetching the variable caused an exception
    """
    try:
        allowed = 'IMPORT_THIS_TO_EXCLUDE_PACKAGE_FROM_MEMORY_PROFILING' not in \
                   dir(sys.modules[".".join(func.__module__.split('.')[:-1])])
        return allowed
    except Exception as exp:
        thread_log.exception('TURBOGEARS: Failed check_memory_profile_package_wide_disable')
        return False


def set_memory_profile_logging(_thread_log, value):
    """
    Sets and logs to console the environment variable that enables memory profiling 
    :param _thread_log: console logger
    :return: 
    """
    os.environ['MEMORY_PROFILE_LOGGING_ON'] = str(value)
    _thread_log.info(' SET MEMORY_PROFILE_LOGGING_ON={}'.format(os.environ['MEMORY_PROFILE_LOGGING_ON']))


def profile_expose_method(profiled_method_wrapper, accept, args, func, kw, exclude_from_memory_profiling):
    """
    Targeted to profile a specific method that wraps HTTP request processing endpoints into database context.  
    :param profiled_method_wrapper: method wrapped around profiled call to be passed in to memory profiler
    :param accept: param specific to profiled call
    :param args: args of a function that is being wrapped by a profiled method
    :param func: function that is being wrapped by a profiled method
    :param kw: kwargs of a function that is being wrapped by a profiled method
    :return: output of a profiled method without modification
    """
    if not exclude_from_memory_profiling and get_memory_profile_logging_on() and \
            check_memory_profile_package_wide_disable(func):
        controller_class = args[0].__class__.__name__ if args and len(args) > 0 else ''
        end_point_name_parts = [s for s in [func.__module__, controller_class, func.__name__] if s != '']
        end_point_name = ".".join(end_point_name_parts)
        is_pympler_on = _is_pympler_profiling_value_on(end_point_name)
        profile_output = {'output': {}}
        if is_pympler_on:
            all_objects = muppy.get_objects()
            all_objects_summary_before = summary.summarize(all_objects)
        memory_profile = memory_usage((_profile_me,
                                       (profile_output, profiled_method_wrapper, func, accept, args, kw),
                                       {}),
                                      interval=0.1)
        output = profile_output['output']
        if is_pympler_on:
            all_objects_summary_after = summary.summarize(all_objects)
            diff = summary.get_diff(all_objects_summary_before, all_objects_summary_after)
            diff_less = summary.format_(diff)
            diff_out = ''
            for s in diff_less:
                diff_out += s+'\n'
            thread_log.info("================ PYMPLER OUTPUT <{}> ==============\n{}".format(end_point_name, diff_out))
        try:

            message = json.dumps({'log_type': 'memory_profile',
                                  'proc_id': os.getpid(),
                                  'name': func.__name__,
                                  'module': func.__module__,
                                  'mem_profile': memory_profile,
                                  'min': min(memory_profile),
                                  'max': max(memory_profile),
                                  'diff': max(memory_profile) - min(memory_profile),
                                  'leaked': memory_profile[-1] - memory_profile[0],
                                  'args': [arg for arg in args[1:]],  # exclude self
                                  'kwargs': kw})
            memory_log.info(message,
                            extra={'controller_module': func.__module__,
                                   'controller_class': controller_class,
                                   'endpoint': func.__name__})
        except Exception as e:
            thread_log.exception('Logger failed: {}'.format(e))
    else:
        output = profiled_method_wrapper(accept, args, func, kw)
    return output


def _profile_me(_output, pass_through_expose_method, _func, _accept, _args, _kwargs):
    """
    Wraps method to return output through a parameter since memory_usage call does not support return of a value from a 
    profiled method
    :param _output: 
    :param pass_through_expose_method: 
    :param _func: 
    :param _accept: 
    :param _args: 
    :param _kwargs: 
    :return: None as the result returned through an _output dictionary value and picked out in above method 
    """
    _output['output'] = pass_through_expose_method(_accept, _args, _func, _kwargs)
