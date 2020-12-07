"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import click
import json
import os

try:
    from nucypher.utilities.clouddeploy import CloudDeployers
except ImportError:
    CloudDeployers = None
from nucypher.cli.utils import setup_emitter
from nucypher.config.characters import StakeHolderConfiguration
from nucypher.cli.commands.stake import group_staker_options, option_config_file, group_general_config


def filter_staker_addresses(stakers, stakes):

    staker_addresses = set()
    for staker in stakers:

        for stake in staker.stakes:
            if stakes:
                if not stake.staker_address in stakes:
                    continue
            staker_addresses.add(stake.staker_address)
    return staker_addresses


@click.group()
def cloudworkers():
    """Manage stakes and other staker-related operations."""

@cloudworkers.command('up')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="aws or digitalocean", default='aws')
@click.option('--aws-profile', help="The cloud provider account profile you'd like to use (an aws profile)", default=None)
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided, nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes. (default is nucypher/nucypher:latest)", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--include-stakeholder', 'stakes', help="limit worker to specified stakeholder addresses", multiple=True)
@click.option('--wipe', help="Clear nucypher configs on existing nodes and start a fresh node with new keys.", default=False, is_flag=True)
@click.option('--prometheus', help="Run Prometheus on workers.", default=False, is_flag=True)
@click.option('--create-unstaked', help="Just create this many nodes.  Don't tie them to any stakes.", type=click.INT, default=0)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING)
@group_general_config
def up(general_config, staker_options, config_file, cloudprovider, aws_profile, remote_provider, nucypher_image, seed_network, sentry_dsn, stakes, wipe, prometheus, create_unstaked, namespace):
    """Creates workers for all stakes owned by the user for the given network."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use this command.  (Please run 'pip install ansible'.)", color="red")
        return
    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers and not create_unstaked:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, stakes)

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file, remote_provider, nucypher_image, seed_network, sentry_dsn, aws_profile, prometheus, namespace=namespace, network=STAKEHOLDER.network)
    if staker_addresses:
        config = deployer.create_nodes(staker_addresses)

    if config.get('instances') and len(config.get('instances')) >= len(staker_addresses):
        emitter.echo('Nodes exist for all requested stakes', color="yellow")
        deployer.deploy_nucypher_on_existing_nodes(staker_addresses, wipe_nucypher=wipe)


@cloudworkers.command('create')
@click.option('--cloudprovider', help="aws or digitalocean", default='aws')
@click.option('--aws-profile', help="The AWS account profile you'd like to use (option not required for DigitalOcean users)", default=None)
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided, nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes. (default is nucypher/nucypher:latest)", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--prometheus', help="Run Prometheus on workers.", default=False, is_flag=True)
@click.option('--count', help="Create this many nodes.", type=click.INT, default=1)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING)
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@group_general_config
def create(general_config, cloudprovider, aws_profile, remote_provider, nucypher_image, seed_network, sentry_dsn, prometheus, count, namespace, network):
    """Creates the required number of workers to be staked later under a namespace"""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use this command.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, None, None, remote_provider, nucypher_image, seed_network, sentry_dsn, aws_profile, prometheus, namespace=namespace, network=network)
    if not namespace:
        emitter.echo("A namespace is required. Choose something to help differentiate between hosts, such as their specific purpose, or even just today's date.", color="red")
        return
    names = [f'{namespace}-{network}-{i}' for i in range(1, count + 1)]
    config = deployer.create_nodes(names, unstaked=True)

    if config.get('instances') and len(config.get('instances')) >= count:
        emitter.echo('The requested number of nodes now exist', color="green")
        deployer.deploy_nucypher_on_existing_nodes(names)


@cloudworkers.command('add')
@click.option('--host-address', help="The IP address or Hostname of the host you are adding.", required=True)
@click.option('--login-name', help="The name username of a user with root privileges we can ssh as on the host.", required=True)
@click.option('--key-path', help="The path to a keypair we will need to ssh into this host", default="~/.ssh/id_rsa.pub")
@click.option('--ssh-port', help="The port this host's ssh daemon is listening on", default=22)
@click.option('--host-nickname', help="A nickname to remember this host by", type=click.STRING, required=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, required=True)
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@group_general_config
def add(general_config, host_address, login_name, key_path, ssh_port, host_nickname, namespace, network):
    """Sets an existing node as the host for the given staker address."""

    emitter = setup_emitter(general_config)
    name = f'{namespace}-{network}-{host_nickname}'

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)
    config = deployer.create_nodes([name], host_address, login_name, key_path, ssh_port)
    print (json.dumps(config, indent=4))
    emitter.echo(f'Success.  Now run `nucypher cloudworkers deploy --namespace {namespace} --remote-provider <an eth provider>` to deploy Nucypher on this node.', color='green')


@cloudworkers.command('add_for_stakes')
@group_staker_options
@option_config_file
@click.option('--staker-address',  help="The staker account address for whom you are adding a worker host.", required=True)
@click.option('--host-address', help="The IP address or Hostname of the host you are adding.", required=True)
@click.option('--login-name', help="The name username of a user with root privileges we can ssh as on the host.", required=True)
@click.option('--key-path', help="The path to a keypair we will need to ssh into this host", default="~/.ssh/id_rsa.pub")
@click.option('--ssh-port', help="The port this host's ssh daemon is listening on", default=22)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING)
@group_general_config
def add_for_stakes(general_config, staker_address, host_address, login_name, key_path, ssh_port, namespace):
    """Sets an existing node as the host for the given staker address."""

    emitter = setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, [staker_address])
    if not staker_addresses:
        emitter.echo(f"Could not find staker address: {staker_address} among your stakes. (try `nucypher stake --list`)", color="red")
        return

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer('generic')(emitter, STAKEHOLDER, config_file, namespace=namespace, network=STAKEHOLDER.network)
    config = deployer.create_nodes(staker_addresses, host_address, login_name, key_path, ssh_port)



@cloudworkers.command('deploy')
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes.", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--wipe', help="Clear your nucypher config and start a fresh node with new keys", default=False, is_flag=True)
@click.option('--prometheus', help="Run Prometheus on workers.", default=False, is_flag=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING)
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--gas-strategy', help="Which gas strategy?  (glacial, slow, medium, fast)", type=click.STRING)
@group_general_config
def deploy(general_config, remote_provider, nucypher_image, seed_network, sentry_dsn, wipe, prometheus, namespace, network, gas_strategy):
    """Deploys NuCypher on existing hardware."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, remote_provider, nucypher_image, seed_network, sentry_dsn, prometheus=prometheus, namespace=namespace, network=network, gas_strategy=gas_strategy)

    emitter.echo(f"found deploying {nucypher_image} on the following existing hosts:")
    for name, hostdata in deployer.config['instances'].items():
        emitter.echo(f'\t{name}: {hostdata["publicaddress"]}', color="yellow")
    deployer.deploy_nucypher_on_existing_nodes(deployer.config['instances'].keys(), wipe_nucypher=wipe)


@cloudworkers.command('update')
@click.option('--remote-provider', help="The blockchain provider for the remote node – e.g. an Infura endpoint address. If not provided nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes.", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--wipe', help="Clear your nucypher config and start a fresh node with new keys", default=False, is_flag=True)
@click.option('--prometheus', help="Run Prometheus on workers.", default=False, is_flag=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING)
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--gas-strategy', help="Which gas strategy?  (glacial, slow, medium, fast)", type=click.STRING)
@group_general_config
def update(general_config, remote_provider, nucypher_image, seed_network, sentry_dsn, wipe, prometheus, namespace, network, gas_strategy):
    """Deploys NuCypher on existing hardware."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, remote_provider, nucypher_image, seed_network, sentry_dsn, prometheus=prometheus, namespace=namespace, network=network, gas_strategy=gas_strategy)

    emitter.echo(f"found deploying {nucypher_image} on the following existing hosts:")
    for name, hostdata in deployer.config['instances'].items():
        emitter.echo(f'\t{name}: {hostdata["publicaddress"]}', color="yellow")
    deployer.update_nucypher_on_existing_nodes(deployer.config['instances'].keys())


@cloudworkers.command('status')
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING)
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@group_general_config
def status(general_config, namespace, network):
    """Displays worker status and updates worker data in stakeholder config"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)
    deployer.get_worker_status(deployer.config['instances'].keys())


@cloudworkers.command('list-namespaces')
@click.option('--network', help="The network whose namespaces you want to see.", type=click.STRING, default='mainnet')
@group_general_config
def list_namespaces(general_config, network):
    """Displays worker status and updates worker data in stakeholder config"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, network=network, pre_config={"namespace": None})
    for ns in os.listdir(deployer.network_config_path):
        emitter.echo(ns)

@cloudworkers.command('list-hosts')
@click.option('--network', help="The network whose hosts you want to see.", type=click.STRING, default='mainnet')
@click.option('--namespace', help="The network whose hosts you want to see.", type=click.STRING, default='local-stakeholders')
@click.option('--include-data', help="Print the config data for each node.", is_flag=True, default=False)
@group_general_config
def list_hosts(general_config, network, namespace, include_data):
    """Prints local config info about known hosts"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, network=network, namespace=namespace)
    for name, data in deployer.get_all_hosts():
        emitter.echo(name)
        if include_data:
            for k, v in data.items():
                emitter.echo(f"\t{k}: {v}")
