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
    def plugin_ips(self):
        return _plugin_ips()

    def addrs_from_relation(self, relation, ip_version=4):
        addrs = []
        attribute = 'addr'

        if ip_version == 6:
            attribute += '6'

        for rid in relation_ids(relation):
            for unit in related_units(rid):
                rel = relation_get(attribute=attribute, rid=rid, unit=unit)

                if rel is None:
                    continue

                if ip_version == 4:
                    # rel will be a domain name. Map it to an IP
                    ip = socket.getaddrinfo(rel, None)[0][4][0]
                    addrs.append(ip)
                else:
                    # We don't use domain names for IPv6.
                    addrs.append(rel)

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
        calico_ctxt['peer_ips6'] = []

        calico_ctxt['plugin_ip'] = self.plugin_ips

        # Our BGP peers are either route reflectors or our cluster peers.
        # Prefer route reflectors.
        calico_ctxt['peer_ips'] = self.addrs_from_relation(
            'bgp-route-reflector'
        )
        calico_ctxt['peer_ips6'] = self.addrs_from_relation(
            'bgp-route-reflector',
            ip_version=6
        )

        if not calico_ctxt['peer_ips']:
            calico_ctxt['peer_ips'] = self.addrs_from_relation('cluster')

        if not calico_ctxt['peer_ips6']:
            calico_ctxt['peer_ips6'] = self.addrs_from_relation(
                'cluster',
                ip_version=6
            )

        return calico_ctxt


class EtcdContext(context.OSContextGenerator):
    interfaces = ['http']

    def __call__(self):
        peers = []
        ctxt = {'cluster': ''}

        for rid in relation_ids('etcd-peer'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                peers.append({
                    'ip': rdata.get('ip'),
                    'port': rdata.get('port'),
                    'name': rdata.get('name'),
                })

        cluster_string = ','.join(
            '{name}=http://{ip}:{port}'.format(**p) for p in peers
        )
        ctxt['cluster'] = cluster_string

        return ctxt
