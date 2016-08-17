import os
import re
import socket
import subprocess

from charmhelpers.core.hookenv import (
    relation_ids,
    related_units,
    relation_get,
    config,
    log,
    unit_get,
)
from charmhelpers.core.host import (
    data_hash,
    file_hash
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
        '''Save the specified data to a file indicated by path, creating the
        parent directory if needed.'''
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w') as stream:
            stream.write(data)
        return path

    def __call__(self):
        for rid in relation_ids('etcd-proxy'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                cluster_string = rdata.get('cluster')
                client_cert = rdata.get('client_cert')
                client_key = rdata.get('client_key')
                client_ca = rdata.get('client_ca')
                if cluster_string and client_cert and client_key and client_ca:
                    # We have all the information we need to run an etcd proxy,
                    # so we could generate and return a complete context.
                    #
                    # However, we don't need to restart the etcd proxy if it is
                    # already running, if there is overlap between the new
                    # 'cluster_string' and the peers that the proxy is already
                    # aware of, and if the TLS credentials are the same as the
                    # proxy already has.
                    #
                    # So, in this block of code we determine whether the etcd
                    # proxy needs to be restarted.  If it doesn't, we return a
                    # null context.  If it does, we generate and return a
                    # complete context with the information needed to do that.

                    # First determine the peers that the existing etcd proxy is
                    # aware of.
                    existing_peers = set([])
                    try:
                        peer_info = subprocess.check_output(['etcdctl',
                                                             '--no-sync',
                                                             'member',
                                                             'list'])
                        for line in peer_info.split('\n'):
                            m = re.search('name=([^ ]+) peerURLs=([^ ]+)',
                                          line)
                            if m:
                                existing_peers.add('%s=%s' % (m.group(1),
                                                              m.group(2)))
                    except:
                        # Probably this means that the proxy was not already
                        # running.  We treat this the same as there being no
                        # existing peers.
                        log('"etcdctl --no-sync member list" call failed')

                    log('Existing etcd peers: %r' % existing_peers)

                    # Now get the peers indicated by the new cluster_string.
                    new_peers = set(cluster_string.split(','))
                    log('New etcd peers: %r' % new_peers)

                    if new_peers & existing_peers:
                        # New and existing peers overlap, so we probably don't
                        # need to restart the etcd proxy.  But check in case
                        # the TLS credentials have changed.
                        log('New and existing etcd peers overlap')

                        existing_cred_hash = (
                            (file_hash('/etc/neutron-calico/etcd_cert') or '?')
                            +
                            (file_hash('/etc/neutron-calico/etcd_key') or '?')
                            +
                            (file_hash('/etc/neutron-calico/etcd_ca') or '?')
                        )
                        log('Existing credentials: %s' % existing_cred_hash)

                        new_cred_hash = (
                            data_hash(client_cert) +
                            data_hash(client_key) +
                            data_hash(client_ca)
                        )
                        log('New credentials: %s' % new_cred_hash)

                        if new_cred_hash == existing_cred_hash:
                            log('TLS credentials unchanged')
                            return {}

                    # We need to start or restart the etcd proxy, so generate a
                    # context with the new cluster string and TLS credentials.
                    return {'cluster': cluster_string,
                            'server_certificate':
                            self._save_data(client_cert,
                                            '/etc/neutron-calico/etcd_cert'),
                            'server_key':
                            self._save_data(client_key,
                                            '/etc/neutron-calico/etcd_key'),
                            'ca_certificate':
                            self._save_data(client_ca,
                                            '/etc/neutron-calico/etcd_ca')}

        return {}
