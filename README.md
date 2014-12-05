# Overview

This subordinate charm provides the Neutron Calico configuration for a compute node.

Once deployed it takes over the management of the Neutron base and plugin configuration on the compute node.

For more information on Calico, check out the [Project Calico homepage](http://www.projectcalico.org/).

# Usage

To deploy (partial deployment of linked charms only):

    juju deploy rabbitmq-server
    juju deploy neutron-api
    juju deploy nova-compute
    juju deploy calico-acl-manager
    juju deploy neutron-calico
    juju add-relation neutron-calico nova-compute
    juju add-relation neutron-calico neutron-api
    juju add-relation neutron-calico rabbitmq-server
    juju add-relation neutron-calico calico-acl-manager

When deploying at scale, you should optionally add a BGP route reflector:

    juju deploy bird
    juju add-relation neutron-calico bird

# Restrictions

It should only be used with OpenStack Icehouse and above and requires a seperate neutron-api service to have been deployed.

# Contact Information

- Find out more on [the Project Calico website](http://www.projectcalico.org/).
- Report bugs with this charm on [GitHub](https://github.com/metaswitch/calico), [Launchpad](https://code.launchpad.net/~cory-benfield/calico-charms/neutron-calico), or on our mailing list as shown below.
- Contact us on our mailing list [here](httpp://www.projectcalico.org/community/).

