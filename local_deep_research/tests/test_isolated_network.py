import pytest
from scripts.isolated_network import network_args, assert_network_matches


def test_network_and_host_alias_cannot_silently_default():
    reference={'HostConfig':{'NetworkMode':'host','ExtraHosts':['proxy.internal:127.0.0.1']}}
    assert network_args(reference)==['--network','host','--add-host','proxy.internal:127.0.0.1']
    assert_network_matches(reference,reference)
    with pytest.raises(ValueError):assert_network_matches(reference,{'HostConfig':{'NetworkMode':'bridge','ExtraHosts':None}})


def test_missing_contract_is_rejected_without_reading_secret_environment():
    with pytest.raises(ValueError):network_args({'HostConfig':{}})
    assert network_args({'HostConfig':{'NetworkMode':'bridge','ExtraHosts':None}})==['--network','bridge']
