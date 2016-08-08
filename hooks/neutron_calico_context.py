import os
import socket

from charmhelpers.core.hookenv import (
    relation_ids,
    related_units,
    relation_get,
    config,
    log,
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
    interfaces = ['etcd-proxy']

    def _save_data(self, data, path):
        ''' Save the specified data to a file indicated by path, creating the
        parent directory if needed.'''
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w') as stream:
            stream.write(data)
        return path

    def __call__(self):
        ctxt = {}
        cluster_string = None
        client_cert = None
        client_key = None
        client_ca = None

        for rid in relation_ids('etcd-proxy'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                cluster_string = cluster_string or rdata.get('cluster')
                client_cert = client_cert or rdata.get('client_cert')
                client_key = client_key or rdata.get('client_key')
                client_ca = client_ca or rdata.get('client_ca')
                if cluster_string and client_cert and client_key and client_ca:
                    break

        if cluster_string:
            ctxt['cluster'] = cluster_string
        if client_cert:
            ctxt['server_certificate'] = \
                self._save_data(client_cert, '/etc/neutron-calico/etcd_cert')
        if client_key:
            ctxt['server_key'] = \
                self._save_data(client_key, '/etc/neutron-calico/etcd_key')
        if client_ca:
            ctxt['ca_certificate'] = \
                self._save_data(client_ca, '/etc/neutron-calico/etcd_ca')

        log('EtcdContext: %r' % ctxt)

        return ctxt
