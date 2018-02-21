import logging
import signal
import os
import sys
import json
import threading
import tempfile
from fluent import handler
from memory_profiler import memory_usage

memory_log = logging.getLogger("memory_profiler")
mem_out_hdlr = logging.StreamHandler(sys.stdout)
mem_out_hdlr.setLevel(logging.INFO)
memory_log.addHandler(mem_out_hdlr)

thread_log = logging.getLogger("memory_profiler_thread_log")
thread_log_hdlr = logging.StreamHandler(sys.stdout)
thread_log_hdlr.setLevel(logging.INFO)
thread_log.addHandler(thread_log_hdlr)
thread_log.setLevel(logging.INFO)

fluentd_format = {
    'hostename': '%(hostname)s',
    'where': '%(controller_module)s.%(controller_class)s.%(endpoint)s'
}

mem_fluent_hdlr = handler.FluentHandler('bazman.memory_profiler', host='fluentd', port=24224)
mem_fluentd_formatter = handler.FluentRecordFormatter(fluentd_format)
mem_fluent_hdlr.setFormatter(mem_fluentd_formatter)
mem_fluent_hdlr.setLevel(logging.INFO)
memory_log.addHandler(mem_fluent_hdlr)

memory_log.setLevel(logging.INFO)


def toggle_memory_profile_via_fifo(thread_log):
    thread_log.info('started toggle_memory_profile_via_fifo thread')
    fifo_name = tempfile.gettempdir()+'/bazman_memory_config_fifo'
    if not os.path.exists(fifo_name):
        os.mkfifo(fifo_name)
    while True:
        with open(fifo_name, 'r') as config_fifo:
            thread_log.info('opened FIFO toggle_memory_profile_via_fifo thread')
            line = config_fifo.readline()[:-1]
            thread_log.info('READ LINE toggle_memory_profile_via_fifo thread ====>' + line)
            toggle_memory_profile_logging(thread_log)

config_thread = threading.Thread(target=toggle_memory_profile_via_fifo, args=(thread_log,), name='toggle_memory_profile_via_fifo')
config_thread.setDaemon(True)
config_thread.start()


def get_memory_profile_logging_on():
    return os.environ.get('MEMORY_PROFILE_LOGGING_ON', 'False') == 'True'


def toggle_memory_profile_logging(thread_log):
    memory_profile_logging_on = get_memory_profile_logging_on()
    os.environ['MEMORY_PROFILE_LOGGING_ON'] = str(not memory_profile_logging_on)
    thread_log.info(' SET MEMORY_PROFILE_LOGGING_ON = ' + str(not memory_profile_logging_on))


def profile_expose_method(pass_through_expose_method, test_expose_method, accept, args, func, kw):
    if get_memory_profile_logging_on():
        profile_output = {'output': {}}
        memory_profile = memory_usage((test_expose_method, (profile_output, func, accept, args, kw), {}), interval=0.1)
        # _profile_me(profile_output, func, accept, args, kw)
        output = profile_output['output']
        controller_class = args[0].__class__.__name__ if args and len(args) > 0 else ''
        message = json.dumps({'log_type': 'memory_profile',
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
    else:
        output = pass_through_expose_method(accept, args, func, kw)
    return output
