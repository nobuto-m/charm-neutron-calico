import socket

from charmhelpers.core.hookenv import (
    relation_ids,
    related_units,
    relation_get,
    config,
    unit_get,
)
from charmhelpers.contrib.openstack import context
from charmhelpers.contrib.openstack.utils import get_host_ip
from charmhelpers.contrib.network.ip import get_address_in_network


def _neutron_security_groups():
    '''
    Inspects current neutron-plugin relation and determine if neutron-api has
    instructed us to use neutron security groups.
    '''
    for rid in relation_ids('neutron-plugin-api'):
        for unit in related_units(rid):
            sec_group = relation_get('neutron-security-groups',
                                     rid=rid,
                                     unit=unit)
            if sec_group is not None:
                return sec_group
    return False


class CalicoPluginContext(context.NeutronContext):
    interfaces = []

    @property
    def plugin(self):
        return 'Calico'

    @property
    def network_manager(self):
        return 'neutron'

    @property
    def neutron_security_groups(self):
        return _neutron_security_groups()

    def calico_ctxt(self):
        calico_ctxt = super(CalicoPluginContext, self).calico_ctxt()
        if not calico_ctxt:
            return {}

        conf = config()
        calico_ctxt['local_ip'] = \
            get_address_in_network(config('os-data-network'),
                                   get_host_ip(unit_get('private-address')))
        calico_ctxt['neutron_security_groups'] = self.neutron_security_groups
        calico_ctxt['use_syslog'] = conf['use-syslog']
        calico_ctxt['verbose'] = conf['verbose']
        calico_ctxt['debug'] = conf['debug']
        calico_ctxt['peer_ips'] = []

        for rid in relation_ids('cluster'):
            for unit in related_units(rid):
                rel = relation_get(attribute='addr', rid=rid, unit=unit)

                if rel is not None:
                    # rel will be a domain name. Map it to an IP
                    ip = socket.getaddrinfo(rel, None)[0][4][0]
                    calico_ctxt['peer_ips'].append(ip)

        return calico_ctxt

