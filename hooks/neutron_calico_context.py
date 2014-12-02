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


def _acl_manager_ips():
    '''
    Inspects current calico-acl-api relation and determines what the IP
    addresses of the ACL managers are.

    Currently multiple ACL managers are not supported by Calico.
    '''
    for rid in relation_ids('calico-acl-api'):
        for unit in related_units(rid):
            acl_mgr = relation_get('manager_addr',
                                   rid=rid,
                                   unit=unit)
            if acl_mgr is not None:
                return acl_mgr

    return ''


def _plugin_ips():
    '''
    Insepcts the current neutron-plugin relation and determines the IP
    address of the neutron-api install, which is where the Calico plugin
    lives.
    '''
    for rid in relation_ids('neutron-plugin-api'):
        for unit in related_units(rid):
            rel = relation_get(attribute='addr', rid=rid, unit=unit)

            if rel is not None:
                # rel will be a domain name. Map it to an IP
                ip = socket.getaddrinfo(rel, None)[0][4][0]
                return ip

    return ''


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

    @property
    def acl_manager_ips(self):
        return _acl_manager_ips()

    @property
    def plugin_ips(self):
        return _plugin_ips()

    def addrs_from_relation(self, relation):
        addrs = []

        for rid in relation_ids(relation):
            for unit in related_units(rid):
                rel = relation_get(attribute='addr', rid=rid, unit=unit)

                if rel is not None:
                    # rel will be a domain name. Map it to an IP
                    ip = socket.getaddrinfo(rel, None)[0][4][0]
                    addrs.append(ip)

        return addrs

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

        # We need the ACL manager IP. Currently we only allow one.
        calico_ctxt['acl_manager_ip'] = self.acl_manager_ips
        calico_ctxt['plugin_ip'] = self.plugin_ips

        # Our BGP peers are either route reflectors or our cluster peers.
        # Prefer route reflectors.
        calico_ctxt['peer_ips'] = self.addrs_from_relation('bgp-route-reflector')

        if not calico_ctxt['peer_ips']:
            calico_ctxt['peer_ips'] = self.addrs_from_relation('cluster')

        return calico_ctxt
