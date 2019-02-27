import datetime
import json
import os
import random

import maya
import pytest

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.agents import PolicyAgent
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MIN_ALLOWED_LOCKED
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.constants import (
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_REGISTRY_FILEPATH, TEMPORARY_DOMAIN)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.policy import generate_random_label
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services

STAKE_VALUE = MIN_ALLOWED_LOCKED * 2


def test_initialize_custom_blockchain_configuration(deployed_blockchain, custom_filepath, click_runner):
    blockchain, deployer_address = deployed_blockchain

    try:

        # Fake the source contract registry
        with open(MOCK_REGISTRY_FILEPATH, 'w') as file:
            file.write('')

        init_args = ('ursula', 'init',
                     '--poa',
                     '--network', str(TEMPORARY_DOMAIN, encoding='utf-8'),
                     '--checksum-address', deployer_address,
                     '--config-root', custom_filepath,
                     '--provider-uri', TEST_PROVIDER_URI,
                     '--registry-filepath', MOCK_REGISTRY_FILEPATH,
                     '--rest-host', MOCK_IP_ADDRESS,
                     '--rest-port', MOCK_URSULA_STARTING_PORT)

        user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
        result = click_runner.invoke(nucypher_cli,
                                     init_args,
                                     input=user_input,
                                     catch_exceptions=False)
        assert result.exit_code == 0

        # Files and Directories
        assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
        assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
        assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

        custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
        assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

        with open(custom_config_filepath, 'r') as config_file:
            raw_config_data = config_file.read()
            config_data = json.loads(raw_config_data)
            assert config_data['provider_uri'] == TEST_PROVIDER_URI
            assert config_data['checksum_public_address'] == deployer_address
            assert str(TEMPORARY_DOMAIN, encoding='utf-8') in config_data['domains']

        init_args = ('ursula', 'run',
                     '--poa',
                     '--dry-run',
                     '--config-file', custom_config_filepath)

        user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
        result = click_runner.invoke(nucypher_cli,
                                     init_args,
                                     input=user_input,
                                     catch_exceptions=False)
        assert result.exit_code == 0

    finally:
        if os.path.isfile(MOCK_REGISTRY_FILEPATH):
            os.remove(MOCK_REGISTRY_FILEPATH)


def test_run_blockchain_development_ursula(click_runner, deployed_blockchain):
    blockchain, deployer_address = deployed_blockchain

    run_args = ('--debug',
                'ursula', 'run',
                '--dev',
                '--lonely',
                '--poa',
                '--dry-run',
                '--provider-uri', TEST_PROVIDER_URI,
                '--rest-host', MOCK_IP_ADDRESS,
                '--checksum-address', deployer_address)

    result = click_runner.invoke(nucypher_cli, run_args, catch_exceptions=False)
    assert result.exit_code == 0


def test_init_ursula_stake(click_runner, deployed_blockchain):
    blockchain, deployer_address = deployed_blockchain

    stake_args = ('ursula', 'stake',
                  '--value', STAKE_VALUE,
                  '--duration', MIN_LOCKED_PERIODS,
                  '--dev',
                  '--poa',
                  '--force',
                  '--provider-uri', TEST_PROVIDER_URI,
                  '--rest-host', MOCK_IP_ADDRESS,
                  '--checksum-address', deployer_address)

    result = click_runner.invoke(nucypher_cli, stake_args, catch_exceptions=False)
    assert result.exit_code == 0

    # Examine the stake on the blockchain
    miner = Miner(checksum_address=deployer_address, is_me=True, blockchain=blockchain)
    assert len(miner.stakes) == 1
    stake = miner.stakes[0]
    start, end, value = stake
    assert (abs(end-start)+1) == MIN_LOCKED_PERIODS
    assert value == STAKE_VALUE


def test_list_ursula_stakes(click_runner, deployed_blockchain):
    blockchain, _deployer_address = deployed_blockchain
    deployer_address, staking_participant, *everyone_else = blockchain.interface.w3.eth.accounts

    stake_args = ('ursula', 'stake', '--list',
                  '--checksum-address', deployer_address,
                  '--dev',
                  '--poa',
                  '--provider-uri', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli, stake_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(STAKE_VALUE) in result.output


def test_ursula_divide_stakes(click_runner, deployed_blockchain):
    blockchain, _deployer_address = deployed_blockchain
    deployer_address, staking_participant, *everyone_else = blockchain.interface.w3.eth.accounts

    divide_args = ('ursula', 'divide-stake',
                   '--checksum-address', deployer_address,
                   '--dev',
                   '--poa',
                   '--force',
                   '--index', 0,
                   '--value', MIN_ALLOWED_LOCKED,
                   '--duration', 10,
                   '--provider-uri', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli,
                                 divide_args,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_KEYRING_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    assert result.exit_code == 0

    stake_args = ('ursula', 'stake', '--list',
                  '--checksum-address', deployer_address,
                  '--dev',
                  '--poa',
                  '--provider-uri', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli, stake_args, catch_exceptions=False)
    assert result.exit_code == 0

    miner = Miner(checksum_address=deployer_address, blockchain=blockchain, is_me=True)
    assert len(miner.stakes) == 2


@pytest.mark.slow
@pytest.mark.skipif('pytest' in TEST_PROVIDER_URI, reason='Time travel is unavailable with non-pyevm providers')
def test_ursula_collect_staking_rewards(click_runner,
                                        deployed_blockchain,
                                        alice_blockchain_test_config,
                                        bob_blockchain_test_config,
                                        random_policy_label,
                                        federated_ursulas):

    blockchain, _deployer_address = deployed_blockchain
    deployer_address, staking_participant, *everyone_else = blockchain.interface.w3.eth.accounts

    # Record the miner's initial balances
    miner = Miner(checksum_address=deployer_address, blockchain=blockchain, is_me=True)
    original_token_balance = miner.token_balance
    original_eth_balance = miner.eth_balance

    # Start up the local fleet
    for teacher in federated_ursulas:
        start_pytest_ursula_services(ursula=teacher)

    teachers = list(federated_ursulas)
    random_teacher = random.choice(teachers)
    teacher_uri = random_teacher.seed_node_metadata(as_teacher_uri=True)

    # Alice creates a policy and grants Bob access
    alice = alice_blockchain_test_config.produce(blockchain=deployed_blockchain,
                                                 network_middleware=MockRestMiddleware(),
                                                 known_nodes=teachers)

    bob = bob_blockchain_test_config.produce(blockchain=blockchain,
                                             network_middleware=MockRestMiddleware(),
                                             known_nodes=teachers)

    _blockchain_policy = alice.grant(bob=bob,
                                     label=random_policy_label,
                                     m=1, n=1,
                                     expiration=maya.now() + datetime.timedelta(days=MIN_LOCKED_PERIODS))

    # Mock the passage of time and staking confirmations
    for period in range(MIN_LOCKED_PERIODS):
        blockchain.time_travel(periods=1)
        miner.confirm_activity()

    collection_args = ('--mock-networking',
                       'ursula', 'collect-reward',
                       '--teacher-uri', teacher_uri,
                       '--checksum-address', deployer_address,
                       '--dev',
                       '--poa',
                       '--force',
                       '--index', 0,
                       '--value', MIN_ALLOWED_LOCKED,
                       '--duration', 10,
                       '--provider-uri', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_KEYRING_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    assert result.exit_code == 0

    new_token_balance = miner.token_balance
    new_eth_balance = miner.eth_balance

    assert new_token_balance > original_token_balance
    assert new_eth_balance >= original_eth_balance