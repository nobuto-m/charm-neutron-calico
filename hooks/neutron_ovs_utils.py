from charmhelpers.contrib.openstack.neutron import neutron_plugin_attribute
from copy import deepcopy

from charmhelpers.contrib.openstack import context, templating
from collections import OrderedDict
from charmhelpers.contrib.openstack.utils import (
        os_release,
)
import neutron_ovs_context
from charmhelpers.core.hookenv import is_relation_made

NOVA_CONF_DIR = "/etc/nova"
NEUTRON_CONF_DIR = "/etc/neutron"
NEUTRON_CONF = '%s/neutron.conf' % NEUTRON_CONF_DIR
NEUTRON_DEFAULT = '/etc/default/neutron-server'
ML2_CONF = '%s/plugins/ml2/ml2_conf.ini' % NEUTRON_CONF_DIR

BASE_RESOURCE_MAP = OrderedDict([
    (NEUTRON_CONF, {
        'services': [],
        'contexts': [neutron_ovs_context.OVSPluginContext()],
    }),
    (ML2_CONF, {
        'services': ['neutron-plugin-openvswitch-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext()],
    }),
])
TEMPLATES = 'templates/'

def determine_packages():
    ovs_pkgs = []
    pkgs = neutron_plugin_attribute('ovs', 'packages',
                                    'neutron')
    for pkg in pkgs:
        ovs_pkgs.extend(pkg)

    return set(ovs_pkgs)

def register_configs(release=None):
    release = release or os_release('nova-common')
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
    if is_relation_made('amqp'):
        resource_map[NEUTRON_CONF]['contexts'].extend(context.AMQPContext())
    else:
        resource_map[NEUTRON_CONF]['contexts'].extend(neutron_ovs_context.NovaComputeAMQPContext())
    return resource_map

def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().iteritems()}