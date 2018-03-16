import logging
import os
import sys
import json
import threading
import tempfile
from fluent import handler
from memory_profiler import memory_usage
from enum import Enum


class MemoryProfilerState(Enum):
    UNKNOWN = (-1, '', None)
    OFF = (0, 'off', False)
    ON = (1, 'on', True)
    ECHO = (2, 'echo', None)

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
            line = config_fifo.readline()[:-1]
            state=_get_state_from_pipe_command(line)
            _thread_log.info('READ LINE toggle_memory_profile_via_fifo thread ====>{}, state: {}'.format(line, state.name))
            if state == MemoryProfilerState.ON or state == MemoryProfilerState.OFF:
                set_memory_profile_logging(_thread_log, state.value[2])
            elif state == MemoryProfilerState.ECHO:
                _thread_log.info('ECHO MEMORY_PROFILE_LOGGING_ON ==> {}'.format(get_memory_profile_logging_on()))


def _get_state_from_pipe_command(command):
    if command.lower() not in [MemoryProfilerState.ON.value[1],
                               MemoryProfilerState.OFF.value[1],
                               MemoryProfilerState.ECHO.value[1]]:
        return MemoryProfilerState.UNKNOWN
    return {MemoryProfilerState.ON.value[1]: MemoryProfilerState.ON,
            MemoryProfilerState.OFF.value[1]: MemoryProfilerState.OFF,
            MemoryProfilerState.ECHO.value[1]: MemoryProfilerState.ECHO}[command.lower()]


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
        profile_output = {'output': {}}
        memory_profile = memory_usage((_profile_me,
                                       (profile_output, profiled_method_wrapper, func, accept, args, kw),
                                       {}),
                                      interval=0.1)
        output = profile_output['output']
        try:
            controller_class = args[0].__class__.__name__ if args and len(args) > 0 else ''
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
