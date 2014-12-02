import os
from charmhelpers.contrib.openstack.neutron import neutron_plugin_attribute
from copy import deepcopy

from charmhelpers.contrib.openstack import context, templating
from collections import OrderedDict
from charmhelpers.contrib.openstack.utils import (
    os_release,
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
FELIX_CONF = '/etc/calico/felix.cfg'
DHCP_CONF = "%s/dhcp_agent.ini" % NEUTRON_CONF_DIR
BIRD_CONF_DIR = "/etc/bird"
BIRD_CONF = "%s/bird.conf" % BIRD_CONF_DIR

BASE_RESOURCE_MAP = OrderedDict([
    (NEUTRON_CONF, {
        'services': ['calico-felix',
                     'neutron-dhcp-agent',
                     'nova-api-metadata'],
        'contexts': [neutron_calico_context.CalicoPluginContext(),
                     context.AMQPContext()],
    }),
    (BIRD_CONF, {
        'services': ['bird'],
        'contexts': [neutron_calico_context.CalicoPluginContext()],
    }),
    (DHCP_CONF, {
        'services': ['neutron-dhcp-agent'],
        'contexts': [neutron_calico_context.CalicoPluginContext()],
    }),
    (FELIX_CONF, {
        'services': ['calico-felix'],
        'contexts': [neutron_calico_context.CalicoPluginContext()],
    })
])
TEMPLATES = 'templates/'


def additional_install_locations():
    '''
    Add any required additional install locations of the charm. This
    will also force an immediate upgrade.
    '''
    # Temporary hack to get the PPA to work.
    os.environ['LANG'] = 'en_US.UTF-8'
    add_source('ppa:cory-benfield/project-calico')
    add_source('ppa:cz.nic-labs/bird')

    apt_update()
    apt_upgrade()

    # The new version of dnsmasq brings in new dependencies, so we need
    # to explicitly install it.
    apt_install(['dnsmasq-base'])

    return


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
    return resource_map


def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().iteritems()}
