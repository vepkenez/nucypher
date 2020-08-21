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

from nucypher.utilities.clouddeploy import CloudDeployers
from nucypher.cli.utils import setup_emitter
from nucypher.config.characters import StakeHolderConfiguration
from nucypher.cli.commands.stake import group_staker_options, option_config_file, group_general_config


def filter_staker_addresses(stakers, stakes):

    staker_addresses = set()
    for staker in stakers:
        for stake in staker.active_stakes:
            if stakes:
                if not stake.staker_address in stakes:
                    continue
            staker_addresses.add(stake.staker_address)
    return staker_addresses


@click.group()
def workers():
    """Manage stakes and other staker-related operations."""

@workers.command('create')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="currently aws", default='aws')
@click.option('--cloud-profile', help="The cloud provider account profile you'd like to use", default=None)
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes.", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--stakes', help="one or more stakers to whom we should limit worker creation", multiple=True)
@group_general_config
def create(general_config, staker_options, config_file, cloudprovider, cloud_profile, remote_provider, nucypher_image, seed_network, sentry_dsn, stakes):
    """Creates workers for all stakes owned by the user for the given network."""

    emitter = setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, stakes)

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file, cloud_profile, remote_provider, nucypher_image, seed_network, sentry_dsn)
    config = deployer.create_nodes_for_stakers(staker_addresses)

    if config.get('instances') and len(config.get('instances')) >= len(staker_addresses):
        emitter.echo('Nodes exist for all active stakers', color="yellow")
        deployer.deploy_nucypher_on_existing_nodes(staker_addresses)


@workers.command('destroy')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="aws or do (or digitalocean)", default='aws')
@click.option('--stakes', help="one or more stakers to whom we should limit worker destruction", multiple=True)
@group_general_config
def destroy(general_config, staker_options, config_file, cloudprovider, stakes):
    """Cleans up all previously created resources for the given netork for the cloud providern"""

    emitter = setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    config_file = config_file or StakeHolderConfiguration.default_filepath()
    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file)
    emitter.echo(str(stakes))
    deployer.destroy_resources(stakes=stakes)


@workers.command('status')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="aws or do (or digitalocean)", default='aws')
@click.option('--stakes', help="one or more stakers to whom we should limit worker destruction", multiple=True)
@group_general_config
def status(general_config, staker_options, config_file, cloudprovider, stakes):
    """Cleans up all previously created resources for the given netork for the cloud providern"""

    emitter = setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    config_file = config_file or StakeHolderConfiguration.default_filepath()
    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file)

    stakers = STAKEHOLDER.get_stakers()
    staker_addresses = filter_staker_addresses(stakers, stakes)

    deployer.get_worker_status(staker_addresses)