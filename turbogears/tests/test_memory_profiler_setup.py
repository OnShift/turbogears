from unittest import TestCase
from turbogears.memory_profiler_setup import _get_state_from_pipe_command, MemoryProfilerState, _process_fifo_input, \
    get_memory_profile_logging_on, _is_pympler_profiling_value_on, _set_pympler_profiling_value
from mock import MagicMock
from hamcrest import assert_that, equal_to


class TestMemoryProfilerSetup(TestCase):
    def test__get_state_from_pipe_command_unknown(self):
        state, params = _get_state_from_pipe_command('sometrash')
        assert_that(state, equal_to(MemoryProfilerState.UNKNOWN))
        assert_that(params, equal_to(None))

    def test__get_state_from_pipe_command_on(self):
        state, params = _get_state_from_pipe_command('on')
        assert_that(state, equal_to(MemoryProfilerState.ON))
        assert_that(params, equal_to(None))
        state, params = _get_state_from_pipe_command('ON')
        assert_that(state, equal_to(MemoryProfilerState.ON))
        assert_that(params, equal_to(None))
        state, params = _get_state_from_pipe_command('On')
        assert_that(state, equal_to(MemoryProfilerState.ON))
        assert_that(params, equal_to(None))

    def test__get_state_from_pipe_command_off(self):
        state, params = _get_state_from_pipe_command('off')
        assert_that(state, equal_to(MemoryProfilerState.OFF))
        assert_that(params, equal_to(None))
        state, params = _get_state_from_pipe_command('OFF')
        assert_that(state, equal_to(MemoryProfilerState.OFF))
        assert_that(params, equal_to(None))
        state, params = _get_state_from_pipe_command('Off')
        assert_that(state, equal_to(MemoryProfilerState.OFF))
        assert_that(params, equal_to(None))

    def test__get_state_from_pipe_command_echo(self):
        state, params = _get_state_from_pipe_command('echo')
        assert_that(state, equal_to(MemoryProfilerState.ECHO))
        assert_that(params, equal_to(None))
        state, params = _get_state_from_pipe_command('ECHO')
        assert_that(state, equal_to(MemoryProfilerState.ECHO))
        assert_that(params, equal_to(None))
        state, params = _get_state_from_pipe_command('Echo')
        assert_that(state, equal_to(MemoryProfilerState.ECHO))
        assert_that(params, equal_to(None))

    def test__get_state_from_pipe_command_pympler(self):
        # no additional paramteres
        state, params = _get_state_from_pipe_command('pympler')
        assert_that(state, equal_to(MemoryProfilerState.UNKNOWN))
        assert_that(params, equal_to(None))

        state, params = _get_state_from_pipe_command('pympler some_controller.someendpoint on')
        assert_that(state, equal_to(MemoryProfilerState.PYMPLER))
        assert_that(params, equal_to({'endpoint': 'some_controller.someendpoint', 'persistence': 'on'}))

        state, params = _get_state_from_pipe_command('pympler some_controller.someendpoint once')
        assert_that(state, equal_to(MemoryProfilerState.PYMPLER))
        assert_that(params, equal_to({'endpoint': 'some_controller.someendpoint', 'persistence': 'once'}))

        state, params = _get_state_from_pipe_command('pympler some_controller.someendpoint off')
        assert_that(state, equal_to(MemoryProfilerState.PYMPLER))
        assert_that(params, equal_to({'endpoint': 'some_controller.someendpoint', 'persistence': 'off'}))

        state, params = _get_state_from_pipe_command('pympler some_controller.someendpoint nonsense')
        assert_that(state, equal_to(MemoryProfilerState.UNKNOWN))
        assert_that(params, equal_to(None))

    def test_toggle_memory_profile_via_fifo_on(self):
        thread_logger = MagicMock(info=MagicMock())
        config_fifo = MagicMock(readline=MagicMock(return_value='ON\n'))
        _process_fifo_input(thread_logger, config_fifo)
        assert_that(get_memory_profile_logging_on(), equal_to(True))

    def test_toggle_memory_profile_via_fifo_off(self):
        thread_logger = MagicMock(info=MagicMock())
        config_fifo = MagicMock(readline=MagicMock(return_value='OFF\n'))
        _process_fifo_input(thread_logger, config_fifo)
        assert_that(get_memory_profile_logging_on(), equal_to(False))

    def test_toggle_memory_profile_via_fifo_pympler_add_enpoint_once(self):
        thread_logger = MagicMock(info=MagicMock())
        endpoint_path = 'magic_controller.end_point'
        config_fifo = MagicMock(readline=MagicMock(return_value='ON\n'))
        _process_fifo_input(thread_logger, config_fifo)
        config_fifo = MagicMock(readline=MagicMock(return_value='pympler {} ONCE\n'.format(endpoint_path)))
        _process_fifo_input(thread_logger, config_fifo)
        assert_that(get_memory_profile_logging_on(), equal_to(True))
        assert_that(_is_pympler_profiling_value_on(endpoint_path), equal_to(True))

    def test_pympler_profiling_value_management(self):
        _set_pympler_profiling_value('test1', 'on')
        _set_pympler_profiling_value('test2', 'ON')
        _set_pympler_profiling_value('test3', 'On')
        _set_pympler_profiling_value('test4', 'ONCE')
        _set_pympler_profiling_value('test5', 'once')
        _set_pympler_profiling_value('test6', 'once')
        # can get more then once
        assert_that(_is_pympler_profiling_value_on('test1'), equal_to(True))
        assert_that(_is_pympler_profiling_value_on('test1'), equal_to(True))
        # can turn off
        assert_that(_is_pympler_profiling_value_on('test2'), equal_to(True))
        _set_pympler_profiling_value('test2', 'off')
        assert_that(_is_pympler_profiling_value_on('test2'), equal_to(False))
        # can read capitalized
        assert_that(_is_pympler_profiling_value_on('test3'), equal_to(True))
        # can read only once
        assert_that(_is_pympler_profiling_value_on('test4'), equal_to(True))
        assert_that(_is_pympler_profiling_value_on('test4'), equal_to(False))
        # can read lower case
        assert_that(_is_pympler_profiling_value_on('test5'), equal_to(True))
        # can turn off a one time execution profiler
        _set_pympler_profiling_value('test6', 'off')
        assert_that(_is_pympler_profiling_value_on('test6'), equal_to(False))

