import os
import shutil
import glob
import netaddr
import netifaces
from charmhelpers.contrib.openstack.neutron import neutron_plugin_attribute
from copy import deepcopy

from charmhelpers.core.hookenv import config, log
from charmhelpers.core.host import (
    mkdir,
    service_stop,
    service_start,
    service_pause
)
from charmhelpers.contrib.openstack import context, templating
from collections import OrderedDict
from charmhelpers.contrib.openstack.utils import (
    os_release,
    get_os_codename_install_source,
)
from charmhelpers.fetch import (
    add_source,
    apt_update,
    apt_upgrade,
    apt_install
)
import neutron_calico_context

NOVA_CONF_DIR = "/etc/nova"
NEUTRON_CONF_DIR = "/etc/neutron"
NEUTRON_CONF = '%s/neutron.conf' % NEUTRON_CONF_DIR
NEUTRON_DEFAULT = '/etc/default/neutron-server'
ML2_CONF = '%s/plugins/ml2/ml2_conf.ini' % NEUTRON_CONF_DIR
FELIX_CONF_DIR = '/etc/calico'
FELIX_CONF = FELIX_CONF_DIR + '/felix.cfg'
DHCP_CONF = "%s/dhcp_agent.ini" % NEUTRON_CONF_DIR
BIRD_CONF_DIR = "/etc/bird"
BIRD_CONF = "%s/bird.conf" % BIRD_CONF_DIR
BIRD6_CONF = "%s/bird6.conf" % BIRD_CONF_DIR

DHCP_AGENT = 'neutron-dhcp-agent'
if get_os_codename_install_source(config('openstack-origin')) >= 'liberty':
    DHCP_AGENT = 'calico-dhcp-agent'

BASE_RESOURCE_MAP = OrderedDict([
    (NEUTRON_CONF, {
        'services': ['calico-felix',
                     DHCP_AGENT,
                     'nova-api-metadata'],
        'contexts': [neutron_calico_context.CalicoPluginContext(),
                     context.AMQPContext()],
    }),
    (DHCP_CONF, {
        'services': [DHCP_AGENT],
        'contexts': [neutron_calico_context.CalicoPluginContext()],
    })
])
BIRD_RESOURCE_MAP = {
    'services': ['bird'],
    'contexts': [neutron_calico_context.CalicoPluginContext()],
}
BIRD6_RESOURCE_MAP = {
    'services': ['bird6'],
    'contexts': [neutron_calico_context.CalicoPluginContext()],
}
TEMPLATES = 'templates/'


def additional_install_locations():
    '''
    Add any required additional install locations of the charm. This
    will also force an immediate upgrade.
    '''
    calico_source = 'ppa:project-calico/icehouse'

    if config('calico-origin') != 'default':
        calico_source = config('calico-origin')
    else:
        release = get_os_codename_install_source(config('openstack-origin'))
        if release in ('icehouse', 'juno', 'kilo'):
            # Prior to the Liberty release, Calico's Nova and Neutron changes
            # were not fully upstreamed, so we need to point to a
            # release-specific PPA that includes Calico-specific Nova and
            # Neutron packages.
            calico_source = 'ppa:project-calico/%s' % release
        else:
            # From Liberty onwards, we can point to a PPA that does not include
            # any patched OpenStack packages, and hence is independent of the
            # OpenStack release.
            calico_source = 'ppa:project-calico/calico-1.4'

    # Force UTF-8 to get the BIRD PPA to work.
    os.environ['LANG'] = 'en_US.UTF-8'
    add_source(calico_source)
    add_source('ppa:cz.nic-labs/bird')

    apt_update()
    apt_upgrade()

    # The new version of dnsmasq brings in new dependencies, so we need
    # to explicitly install it.
    apt_install(['dnsmasq-base'])

    return


def maybe_create_felix_cfg():
    if config('disable-calico-usage-reporting'):
        # Write a Felix config file to disable Calico usage reporting.
        # (Otherwise we don't need any Felix config.)
        mkdir(FELIX_CONF_DIR, perms=0o755)
        with open(FELIX_CONF, 'w') as f:
            f.write('''[global]
UsageReportingEnabled = false
''')


def determine_packages():
    return neutron_plugin_attribute('Calico', 'packages', 'neutron')


def register_configs(release=None):
    release = release or os_release('neutron-common', base='icehouse')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)
    for cfg, rscs in resource_map().iteritems():
        configs.register(cfg, rscs['contexts'])
    return configs


def resource_map():
    '''
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    '''
    resource_map = deepcopy(BASE_RESOURCE_MAP)

    if not config('keep-bird-config'):
        # Service config allows us to change the BIRD config.
        resource_map[BIRD_CONF] = BIRD_RESOURCE_MAP
        if config('enable-ipv6'):
            resource_map[BIRD6_CONF] = BIRD6_RESOURCE_MAP
    else:
        log('keep-bird-config tells us not to touch existing BIRD config')

    return resource_map


def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().iteritems()}


def local_ipv6_address():
    '''
    Determines the IPv6 address to use to contact this machine. Excludes
    link-local addresses.

    Currently only returns the first valid IPv6 address found.
    '''
    for iface in netifaces.interfaces():
        addresses = netifaces.ifaddresses(iface)

        for addr in addresses.get(netifaces.AF_INET6, []):
            # Make sure we strip any interface specifier from the address.
            addr = netaddr.IPAddress(addr['addr'].split('%')[0])

            if not (addr.is_link_local() or addr.is_loopback()):
                return str(addr)


def force_etcd_restart():
    '''
    If etcd has been reconfigured we need to force it to fully restart.
    This is necessary because etcd has some config flags that it ignores
    after the first time it starts, so we need to make it forget them.
    '''
    service_stop('etcd')
    for directory in glob.glob('/var/lib/etcd/*'):
        shutil.rmtree(directory)
    service_start('etcd')


def configure_dhcp_agents():
    '''
    If we're using the Calico DHCP agent, ensure that the Neutron DHCP agent is
    stopped and disabled.
    '''
    if DHCP_AGENT == 'calico-dhcp-agent':
        # Stop and disable the Neutron DHCP agent.
        service_pause('neutron-dhcp-agent')
