#!/usr/bin/python

import sys
import os

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
    apt_install, apt_update, apt_upgrade
)

from neutron_calico_utils import (
    determine_packages,
    register_configs,
    restart_map,
)

from subprocess import check_call

hooks = Hooks()
CONFIGS = register_configs()

def calico_hack():
    env = os.environ.copy()

    check_call(
        'curl -L http://binaries.projectcalico.org/repo/key | '
        'apt-key add -',
        shell=True
    )

    with open('/etc/apt/sources.list.d/calico.list', 'w') as f:
        f.write('deb http://binaries.projectcalico.org/repo ./')

    with open('/etc/apt/preferences', 'w') as f:
        f.write('Package: *\nPin: origin binaries.projectcalico.org\nPin-Priority: 1001\n')

    env['LANG'] = 'en_US.UTF-8'
    check_call(['add-apt-repository', 'ppa:cz.nic-labs/bird'], env=env)

    apt_update()
    apt_upgrade(options=['--force-yes'], dist=True)

    return


@hooks.hook()
def install():
    # FIXME: Remove terrible Calico install hack.
    calico_hack()

    apt_update()
    pkgs = determine_packages()
    for pkg in pkgs:
        apt_install(pkg, fatal=True)


@hooks.hook('neutron-plugin-relation-changed')
@hooks.hook('neutron-plugin-api-relation-changed')
@hooks.hook('config-changed')
@hooks.hook('cluster-relation-changed')
@hooks.hook('cluster-relation-departed')
@restart_on_change(restart_map())
def config_changed():
    CONFIGS.write_all()


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
                 addr=unit_private_ip())


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))


if __name__ == '__main__':
    main()
