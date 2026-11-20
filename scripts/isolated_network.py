"""Preserve explicit Docker network/host mappings without exposing environment.

Helpers only produce argv/compare inspect data; they launch nothing and change
no service. Other launch properties require their own checks.
"""


def network_args(reference):
    config = reference['HostConfig']
    mode = config.get('NetworkMode')
    hosts = config.get('ExtraHosts') or []
    if not isinstance(mode,str) or not mode or not isinstance(hosts,list) or any(not isinstance(h,str) or not h for h in hosts):
        raise ValueError('Missing explicit network contract')
    args = ['--network',mode]
    for mapping in hosts:
        args += ['--add-host',mapping]
    return args


def assert_network_matches(reference, candidate):
    if network_args(reference) != network_args(candidate):
        raise ValueError('Isolated attempt network differs from reference')
