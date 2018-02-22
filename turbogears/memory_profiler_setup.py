import logging
import signal
import os
import sys
import json
import threading
import tempfile
from fluent import handler
from memory_profiler import memory_usage

# memory profiler system configuration
FLUENTD_HOST_NAME = os.environ.get('FLUENTD_HOST_NAME', 'fluentd')
_fluentd_port_str = os.environ.get('FLUENTD_PORT', '24224')
FLUENTD_PORT = int(_fluentd_port_str) if _fluentd_port_str.isdigit() else 24224
TURBOGEARS_PROFILER_FIFO_PATH = os.environ.get('TURBOGEARS_PROFILER_FIFO_PATH',
                                               '{}/turbogears_memory_config_fifo'.format(tempfile.gettempdir()))
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
                'TURBOGEARS_PROFILER_LOG_TO_CONSOLE={}'.format(FLUENTD_HOST_NAME,FLUENTD_PORT,
                                                               TURBOGEARS_PROFILER_FIFO_PATH,
                                                               TURBOGEARS_PROFILER_LOG_TO_CONSOLE)
                )


def toggle_memory_profile_via_fifo(_thread_log):
    """
    execution body of a thread that monitors any input on a named pipe located at /tmp/turbogears_memory_config_fifo.
    Whenever any value with a new line is pushed into the FIFO the thread will trigger the toggle of an environment
    variable and turn memory profiling ON or OFF
    :param _thread_log: console logger
    :return: 
    """
    _thread_log.info('started toggle_memory_profile_via_fifo thread PID({})'.format(os.getpid()))
    fifo_name = TURBOGEARS_PROFILER_FIFO_PATH
    if not os.path.exists(fifo_name):
        os.mkfifo(fifo_name)
    while True:
        with open(fifo_name, 'r') as config_fifo:
            _thread_log.info('opened FIFO toggle_memory_profile_via_fifo thread')
            line = config_fifo.readline()[:-1]
            _thread_log.info('READ LINE toggle_memory_profile_via_fifo thread ====>{}'.format(line))
            toggle_memory_profile_logging(_thread_log)


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


def toggle_memory_profile_logging(_thread_log):
    """
    Toggles and logs to console the environment variable that enables memory profiling 
    :param _thread_log: console logger
    :return: 
    """
    memory_profile_logging_on = get_memory_profile_logging_on()
    os.environ['MEMORY_PROFILE_LOGGING_ON'] = str(not memory_profile_logging_on)
    _thread_log.info(' SET MEMORY_PROFILE_LOGGING_ON={}'.format(not memory_profile_logging_on))


def profile_expose_method(profiled_method_wrapper, accept, args, func, kw):
    """
    Targeted to profile a specific method that wraps HTTP request processing endpoints into database context.  
    :param profiled_method_wrapper: method wrapped around profiled call to be passed in to memory profiler
    :param accept: param specific to profiled call
    :param args: args of a function that is being wrapped by a profiled method
    :param func: function that is being wrapped by a profiled method
    :param kw: kwargs of a function that is being wrapped by a profiled method
    :return: output of a profiled method without modification
    """
    if get_memory_profile_logging_on():
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
            thread_log.exception("failed to log memory profile for {}".foramt(func.__name__))
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
