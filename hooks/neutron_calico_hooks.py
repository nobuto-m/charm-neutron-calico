#!/usr/bin/python

import sys

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    log,
    relation_set,
    unit_private_ip
)

from charmhelpers.core.host import (
    restart_on_change
)

from charmhelpers.fetch import (
    apt_install, apt_update
)

from neutron_calico_utils import (
    determine_packages,
    register_configs,
    restart_map,
    additional_install_locations,
    local_ipv6_address,
    force_etcd_restart,
)

from neutron_calico_context import EtcdContext

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook()
def install():
    additional_install_locations()
    apt_update()
    pkgs = determine_packages()
    for pkg in pkgs:
        apt_install(pkg, fatal=True)


@hooks.hook('neutron-plugin-relation-changed')
@hooks.hook('neutron-plugin-api-relation-changed')
@hooks.hook('cluster-relation-changed')
@hooks.hook('cluster-relation-departed')
@hooks.hook('bgp-route-reflector-relation-changed')
@hooks.hook('bgp-route-reflector-relation-departed')
@restart_on_change(restart_map())
def generic_relation_changed():
    CONFIGS.write_all()


@hooks.hook('config-changed')
@restart_on_change(restart_map())
def config_changed():
    global CONFIGS
    CONFIGS = register_configs()
    CONFIGS.write_all()


@hooks.hook('neutron-plugin-relation-joined')
def neutron_plugin_joined(relation_id=None):
    rel_data = {
        'enable-metadata': 'True',
    }
    relation_set(relation_id=relation_id, **rel_data)


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 username=config('rabbit-user'),
                 vhost=config('rabbit-vhost'))


@hooks.hook('amqp-relation-changed')
@hooks.hook('amqp-relation-departed')
@restart_on_change(restart_map())
def amqp_changed():
    if 'amqp' not in CONFIGS.complete_contexts():
        log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write_all()


@hooks.hook('cluster-relation-joined')
def cluster_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 addr=unit_private_ip(),
                 addr6=local_ipv6_address())


@hooks.hook('bgp-route-reflector-relation-joined')
def bgp_route_reflector_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 addr=unit_private_ip(),
                 addr6=local_ipv6_address())


@hooks.hook('etcd-proxy-relation-joined')
@hooks.hook('etcd-proxy-relation-changed')
def etcd_proxy_force_restart(relation_id=None):
    # note(cory.benfield): Mostly etcd does not require active management,
    # but occasionally it does require a full config nuking. This does not
    # play well with the standard neutron-api config management, so we
    # treat etcd like the special snowflake it insists on being.
    CONFIGS.register('/etc/init/etcd.conf', [EtcdContext()])
    CONFIGS.write('/etc/init/etcd.conf')

    if 'etcd-proxy' in CONFIGS.complete_contexts():
        force_etcd_restart()


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))


if __name__ == '__main__':
    main()
