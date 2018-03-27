pympler_end_points = {}


def _is_pympler_profiling_value_on(endpoint_path):
    """
    Check if profiling for path is requested and toggle off if it's set to run once
    :param endpoint_path: python path parameter to be matche to dict key
    :return: True if pympler profiling is configured to be triggered for this endpoint else False
    """
    if not endpoint_path in pympler_end_points:
        return False
    if pympler_end_points[endpoint_path].lower() == 'once':
        del pympler_end_points[endpoint_path]
        return True
    elif pympler_end_points[endpoint_path].lower() == 'on':
        return True
    return False


def _set_pympler_profiling_value(endpoint_path, value):
    """
    Set up endpoints to be profiled with pympler
    :param endpoint_path: full python path to end point including module and class
    :param value: ON to run over and over, ONCE to run once and remove, OFF to remoce drom the list
    :return: None
    """
    if value.lower() in ['on', 'once']:
        pympler_end_points[endpoint_path] = value
    elif value.lower() == 'off':
        del pympler_end_points[endpoint_path]