import json
import os

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MIN_ALLOWED_LOCKED
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import (
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_REGISTRY_FILEPATH, TESTER_DOMAIN)


def test_initialize_custom_blockchain_configuration(deployed_blockchain, custom_filepath, click_runner):
    blockchain, deployer_address = deployed_blockchain

    try:

        # Fake the source contract registry
        with open(MOCK_REGISTRY_FILEPATH, 'w') as file:
            file.write('')

        init_args = ('ursula', 'init',
                     '--poa',
                     '--network', TESTER_DOMAIN,
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
            assert TESTER_DOMAIN in config_data['domains']

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


def test_run_geth_development_ursula(click_runner, deployed_blockchain):
    blockchain, deployer_address = deployed_blockchain

    run_args = ('ursula', 'run',
                '--dev',
                '--debug',
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
                  '--value', MIN_ALLOWED_LOCKED,
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
    assert value == MIN_ALLOWED_LOCKED


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
    assert str(MIN_ALLOWED_LOCKED) in result.output