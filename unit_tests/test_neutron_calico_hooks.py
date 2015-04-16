
from mock import MagicMock, patch, call
from test_utils import CharmTestCase


with patch('charmhelpers.core.hookenv.config') as config:
    config.return_value = 'neutron'
    import neutron_calico_utils as utils

_reg = utils.register_configs
_map = utils.restart_map

utils.register_configs = MagicMock()
utils.restart_map = MagicMock()

import neutron_calico_hooks as hooks

utils.register_configs = _reg
utils.restart_map = _map

TO_PATCH = [
    'apt_update',
    'apt_install',
    'config',
    'CONFIGS',
    'determine_packages',
    'log',
    'relation_set',
    'additional_install_locations',
    'register_configs',
    'force_etcd_restart',
]
NEUTRON_CONF_DIR = "/etc/neutron"

NEUTRON_CONF = '%s/neutron.conf' % NEUTRON_CONF_DIR


class NeutronCalicoHooksTests(CharmTestCase):

    def setUp(self):
        super(NeutronCalicoHooksTests, self).setUp(hooks, TO_PATCH)

        self.config.side_effect = self.test_config.get

    def _call_hook(self, hookname):
        hooks.hooks.execute([
            'hooks/{}'.format(hookname)])

    def test_install_hook(self):
        _pkgs = ['foo', 'bar']
        self.determine_packages.return_value = [_pkgs]
        self._call_hook('install')
        self.apt_update.assert_called_with()
        self.apt_install.assert_has_calls([
            call(_pkgs, fatal=True),
        ])

    def test_config_changed(self):
        self.register_configs.return_value = self.CONFIGS
        self._call_hook('config-changed')
        self.assertTrue(self.CONFIGS.write_all.called)
        self.assertTrue(self.register_configs.called)

    def test_amqp_joined(self):
        self._call_hook('amqp-relation-joined')
        self.relation_set.assert_called_with(
            username='neutron',
            vhost='openstack',
            relation_id=None
        )

    def test_amqp_changed(self):
        self.CONFIGS.complete_contexts.return_value = ['amqp']
        self._call_hook('amqp-relation-changed')
        self.assertTrue(self.CONFIGS.write.called_with(NEUTRON_CONF))

    def test_amqp_departed(self):
        self._call_hook('amqp-relation-departed')
        self.assertTrue(self.CONFIGS.write.called_with(NEUTRON_CONF))

    def test_etcd_peer_joined(self):
        self._call_hook('etcd-peer-relation-joined')
        self.assertTrue(self.CONFIGS.register.called)
        self.CONFIGS.write.assert_called_with('/etc/init/etcd.conf')
        self.force_etcd_restart.assert_called_once_with()
