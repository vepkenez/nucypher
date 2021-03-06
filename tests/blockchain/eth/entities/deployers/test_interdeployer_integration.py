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
import os

import pytest
from eth_utils import keccak
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent, AdjudicatorAgent
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               PolicyManagerDeployer,
                                               AdjudicatorDeployer,
                                               ContractDeployer,
                                               DispatcherDeployer)


@pytest.mark.slow()
def test_deploy_ethereum_contracts(session_testerchain, deployment_progress):
    testerchain = session_testerchain

    origin, *everybody_else = testerchain.client.accounts

    #
    # Nucypher Token
    #
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    assert token_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_deployed

    token_deployer.deploy(progress=deployment_progress)
    assert token_deployer.is_deployed
    assert len(token_deployer.contract_address) == 42

    token_agent = NucypherTokenAgent(blockchain=testerchain)
    assert len(token_agent.contract_address) == 42
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert len(another_token_agent.contract_address) == 42
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # StakingEscrow
    #
    stakers_escrow_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    staking_escrow_deployer = StakingEscrowDeployer(
        blockchain=testerchain,
        deployer_address=origin)
    assert staking_escrow_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed

    staking_escrow_deployer.deploy(secret_hash=keccak(stakers_escrow_secret), progress=deployment_progress)
    assert staking_escrow_deployer.is_deployed
    assert len(staking_escrow_deployer.contract_address) == 42

    staking_agent = StakingEscrowAgent(blockchain=testerchain)
    assert len(staking_agent.contract_address) == 42
    assert staking_agent.contract_address == staking_escrow_deployer.contract_address

    another_staking_agent = staking_escrow_deployer.make_agent()
    assert len(another_staking_agent.contract_address) == 42
    assert another_staking_agent.contract_address == staking_escrow_deployer.contract_address == staking_agent.contract_address


    #
    # Policy Manager
    #
    policy_manager_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        blockchain=testerchain,
        deployer_address=origin)

    assert policy_manager_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_deployed

    policy_manager_deployer.deploy(secret_hash=keccak(policy_manager_secret), progress=deployment_progress)
    assert policy_manager_deployer.is_deployed
    assert len(policy_manager_deployer.contract_address) == 42

    policy_agent = policy_manager_deployer.make_agent()
    assert len(policy_agent.contract_address) == 42
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    another_policy_agent = policy_manager_deployer.make_agent()
    assert len(another_policy_agent.contract_address) == 42
    assert another_policy_agent.contract_address == policy_manager_deployer.contract_address == policy_agent.contract_address


    #
    # Adjudicator
    #
    adjudicator_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    adjudicator_deployer = AdjudicatorDeployer(
        blockchain=testerchain,
        deployer_address=origin)

    assert adjudicator_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert adjudicator_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not adjudicator_deployer.is_deployed

    adjudicator_deployer.deploy(secret_hash=keccak(adjudicator_secret), progress=deployment_progress)
    assert adjudicator_deployer.is_deployed
    assert len(adjudicator_deployer.contract_address) == 42

    adjudicator_agent = adjudicator_deployer.make_agent()
    assert len(adjudicator_agent.contract_address) == 42
    assert adjudicator_agent.contract_address == adjudicator_deployer.contract_address

    another_adjudicator_agent = AdjudicatorAgent()
    assert len(another_adjudicator_agent.contract_address) == 42
    assert another_adjudicator_agent.contract_address == adjudicator_deployer.contract_address == adjudicator_agent.contract_address

    # overall deployment steps must match aggregated individual expected number of steps
    all_deployment_transactions = token_deployer.deployment_steps + staking_escrow_deployer.deployment_steps + \
                                  policy_manager_deployer.deployment_steps + adjudicator_deployer.deployment_steps
    assert deployment_progress.num_steps == len(all_deployment_transactions)
